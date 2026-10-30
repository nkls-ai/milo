import asyncio
import json
import stat
import sys
from pathlib import Path

import pytest

from milo.adapters.harness.claude_live import ClaudeLiveModel, content
from milo.core.ports import LiveModel
from milo.core.registry import LIVE_MODELS, ConfigError
from milo.core.types import HarnessError, Usage

# Speaks the stream-json protocol of `claude -p --input-format stream-json`. The user text picks the
# behaviour: "slow" streams ticks until interrupted, "die" exits, "fail" returns an error result,
# "prompt" says the system prompt, anything else is echoed word by word.
FAKE_CLAUDE = r'''
import json, os, select, sys, time

argv = sys.argv[1:]
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as f:
    f.write(json.dumps(argv) + "\n")
system_prompt = argv[argv.index("--system-prompt") + 1]
buf = b""

def lines(timeout):
    global buf
    out = []
    while select.select([0], [], [], timeout)[0]:
        chunk = os.read(0, 65536)
        if not chunk:
            sys.exit(0)
        buf += chunk
        timeout = 0
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        out.append(json.loads(line))
    return out

def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()

def delta(text):
    emit({"type": "stream_event", "event": {"type": "content_block_delta", "index": 0,
                                            "delta": {"type": "text_delta", "text": text}}})

def result(n, subtype="success", is_error=False, text=""):
    emit({"type": "result", "subtype": subtype, "is_error": is_error, "result": text,
          "usage": {"input_tokens": 3, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 0,
                    "output_tokens": n}})

def interrupted(msgs):
    for m in msgs:
        if m.get("type") == "control_request":
            emit({"type": "control_response", "response": {"subtype": "success", "request_id": m["request_id"]}})
            return True
    return False

pending = []
while True:
    msgs = pending or lines(None)
    pending = []
    for i, msg in enumerate(msgs):
        if msg.get("type") == "control_request":
            interrupted([msg])
            continue
        text = msg["message"]["content"]
        emit({"type": "system", "subtype": "status"})
        emit({"type": "stream_event", "event": {"type": "message_start"}})
        if text == "die":
            sys.exit(3)
        if text == "fail":
            result(0, "error_during_execution", True, "overloaded")
            continue
        if text == "slow":
            for n in range(200):
                delta(f"tick{n} ")
                if interrupted(lines(0.02)):
                    result(n, "error_during_execution", True)
                    break
            continue
        words = [system_prompt] if text == "prompt" else text.split()
        for w in words:
            delta(w + " ")
        emit({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
        result(len(words))
'''


@pytest.fixture
def fake_claude(tmp_path, monkeypatch) -> str:
    path = tmp_path / "claude"
    path.write_text(f"#!{sys.executable}\n" + FAKE_CLAUDE)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(tmp_path / "claude.log"))
    return str(path)


def launches(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "claude.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def live(ctx, binary: str, **options) -> ClaudeLiveModel:
    return LIVE_MODELS.create("claude_live", {"binary": binary, **options}, ctx)


async def collect(model: ClaudeLiveModel, text: str) -> list[str]:
    return [d async for d in model.turn(text)]


def test_deltas_stream_in_order_and_usage_is_parsed(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude, model="claude-haiku-5-5", effort="medium")
        assert isinstance(model, LiveModel)
        try:
            first = await collect(model, "hello there Milo")
            assert first == ["hello ", "there ", "Milo "]
            assert model.last_usage == Usage(103, 100, 3)
            assert await collect(model, "again") == ["again "]
            assert model.last_usage == Usage(103, 100, 1)
        finally:
            await model.close()

    asyncio.run(main())
    [args] = launches(tmp_path)  # one process for both turns
    assert args[args.index("--model") + 1] == "claude-haiku-5-5"
    assert args[args.index("--effort") + 1] == "medium"
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--system-prompt") + 1] == ""  # turn() without start()
    for flag in ("--include-partial-messages", "--no-session-persistence", "--strict-mcp-config"):
        assert flag in args
    assert args[args.index("--input-format") + 1] == "stream-json"


def test_interrupt_mid_reply_stops_output_and_next_turn_works(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude)
        try:
            got = []
            async for delta in model.turn("slow"):
                got.append(delta)
                if len(got) == 3:
                    await model.interrupt()
            assert got == ["tick0 ", "tick1 ", "tick2 "]
            assert model.last_usage == Usage()  # the interrupted turn's usage is not reported twice
            assert await collect(model, "still alive") == ["still ", "alive "]
            await model.interrupt()  # no turn running: nothing happens
            assert await collect(model, "ok") == ["ok "]
        finally:
            await model.close()

    asyncio.run(main())
    assert len(launches(tmp_path)) == 1  # the process survived the interrupt


def test_abandoned_turn_leaves_the_stream_clean(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude)
        try:
            gen = model.turn("slow")
            assert await anext(gen) == "tick0 "
            await gen.aclose()
            assert await collect(model, "next one") == ["next ", "one "]

            task = asyncio.create_task(collect(model, "slow"))
            await asyncio.sleep(0.1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await collect(model, "after cancel") == ["after ", "cancel "]
        finally:
            await model.close()

    asyncio.run(main())
    assert len(launches(tmp_path)) == 1


def test_process_death_is_transient_and_next_turn_restarts(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude)
        try:
            await model.start("be brief")
            with pytest.raises(HarnessError, match="stopped") as e:
                await collect(model, "die")
            assert e.value.transient
            assert await collect(model, "prompt") == ["be brief "]  # restarted with the same prompt
        finally:
            await model.close()

    asyncio.run(main())
    assert len(launches(tmp_path)) == 2


def test_error_result_raises(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude)
        try:
            with pytest.raises(HarnessError, match="overloaded"):
                await collect(model, "fail")
            assert await collect(model, "fine") == ["fine "]
        finally:
            await model.close()

    asyncio.run(main())


def test_start_replaces_the_process_with_the_new_prompt(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude)
        try:
            await model.start("You are Milo.")
            assert await collect(model, "prompt") == ["You are Milo. "]
            old = model._session.proc
            await model.start("You are Milo, v2.")
            assert old.returncode is not None
            assert await collect(model, "prompt") == ["You are Milo, v2. "]
        finally:
            await model.close()
        assert model._session is None

    asyncio.run(main())
    prompts = [a[a.index("--system-prompt") + 1] for a in launches(tmp_path)]
    assert prompts == ["You are Milo.", "You are Milo, v2."]
    assert (ctx.state_dir / "live").is_dir()  # the process runs outside the workspace


def test_missing_binary_is_a_permanent_harness_error(tmp_path, ctx):
    async def main():
        with pytest.raises(HarnessError, match="could not start") as e:
            await collect(live(ctx, str(tmp_path / "nope")), "hi")
        assert not e.value.transient

    asyncio.run(main())


def test_unknown_option_is_a_config_error(ctx):
    with pytest.raises(ConfigError, match=r"unknown key.*\[chat.claude_live\].*tmeout_s"):
        LIVE_MODELS.create("claude_live", {"tmeout_s": 1}, ctx)


def test_a_screenshot_goes_along_as_a_base64_image_block(tmp_path):
    png = tmp_path / "look.png"
    png.write_bytes(b"\x89PNG")
    assert content("hi") == "hi"
    assert content("what's this", [png, tmp_path / "gone.png"]) == [
        {"type": "text", "text": "what's this"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw=="}},
    ]


def test_start_primes_the_conversation_so_the_first_turn_is_fast(tmp_path, ctx, fake_claude):
    from milo.adapters.harness.claude_live import PRIME_TEXT

    async def main():
        model = live(ctx, fake_claude)
        try:
            await model.start("You are Milo.")
            first = await collect(model, "hello there")  # waits for the priming reply, never sees it
            assert first == ["hello ", "there "]
        finally:
            await model.close()
        unprimed = live(ctx, fake_claude, prime=False)
        try:
            await unprimed.start("You are Milo.")
            assert unprimed._priming is None
        finally:
            await unprimed.close()

    asyncio.run(main())
    assert PRIME_TEXT.startswith("("), "reads as a stage direction, not as something the user said"


def test_close_while_priming_stops_cleanly(tmp_path, ctx, fake_claude):
    async def main():
        model = live(ctx, fake_claude)
        await model.start("You are Milo.")
        await model.close()
        assert model._session is None and model._priming is None

    asyncio.run(main())
