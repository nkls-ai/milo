import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from milo.adapters.harness import _binary
from milo.adapters.harness.claude import ClaudeHarness, parse_result
from milo.adapters.harness.codex import CodexHarness, parse_events
from milo.core.registry import HARNESSES, ConfigError
from milo.core.types import Emotion, HarnessError, Reply, Usage

# Captured from `codex exec --json --output-schema` (codex-cli 0.164).
CODEX_EVENTS = """\
{"type":"thread.started","thread_id":"01a189d8-3ee8-7c13-bc63-bee05975fcea"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"{\\"emotion\\":\\"happy\\",\\"say\\":\\"Hi Niklas, nice to meet you!\\"}"}}
{"type":"turn.completed","usage":{"input_tokens":18767,"cached_input_tokens":0,"cache_write_input_tokens":0,"output_tokens":27,"reasoning_output_tokens":0}}
"""

CLAUDE_RESULT = json.dumps({
    "type": "result", "is_error": False, "session_id": "s1", "result": "",
    "structured_output": {"emotion": "excited", "say": "On it!"},
    "usage": {"input_tokens": 10, "cache_read_input_tokens": 5000, "cache_creation_input_tokens": 20,
              "output_tokens": 7},
})


def fake_cli(tmp_path: Path, script: str, name: str = "fake-cli") -> str:
    """A shell script standing in for codex/claude. Records its argv and cwd next to itself."""
    path = tmp_path / name
    log = tmp_path / f"{name}.args"
    path.write_text(f'#!/bin/sh\npwd > "{log}"\nfor a in "$@"; do echo "$a" >> "{log}"; done\n' + script)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def recorded(binary: str) -> tuple[str, list[str]]:
    lines = Path(binary + ".args").read_text().splitlines()
    return lines[0], lines[1:]


# ---- codex


def test_parse_codex_events():
    thread, text, usage, error = parse_events(CODEX_EVENTS.splitlines())
    assert thread == "01a189d8-3ee8-7c13-bc63-bee05975fcea"
    assert error is None
    assert usage == Usage(18767, 0, 27)
    reply = Reply.from_model_text(text, usage, thread)
    assert (reply.emotion, reply.say) == (Emotion.HAPPY, "Hi Niklas, nice to meet you!")


def test_parse_codex_failure():
    lines = ['{"type":"thread.started","thread_id":"t"}', '{"type":"turn.failed","error":{"message":"rate limited"}}']
    assert parse_events(lines)[3] == "rate limited"


def test_reply_falls_back_to_raw_text_and_neutral():
    reply = Reply.from_model_text("not json at all", Usage(), None)
    assert (reply.emotion, reply.say) == (Emotion.NEUTRAL, "not json at all")
    assert Reply.from_model_text('{"emotion":"furious","say":"hi"}', Usage(), None).emotion == Emotion.NEUTRAL


def test_codex_resume_command_keeps_sandbox(tmp_path):
    h = CodexHarness("codex", tmp_path, tmp_path / "schema.json", sandbox="read-only")
    first = h.command("hello", None)
    resumed = h.command("again", "abc")
    assert first[:2] == ["codex", "exec"] and "resume" not in first
    assert resumed[:4] == ["codex", "exec", "resume", "abc"]
    for cmd in (first, resumed):
        assert 'sandbox_mode="read-only"' in cmd
        assert "--sandbox" not in cmd
        assert cmd[-2] == "--"
    assert (first[-1], resumed[-1]) == ("hello", "again")
    assert json.loads((tmp_path / "schema.json").read_text())["required"] == ["emotion", "say"]


def codex(ctx, binary: str, **options) -> CodexHarness:
    return HARNESSES.create("codex", {"binary": binary, **options}, ctx)


def test_codex_adapter_against_fake_binary(tmp_path, ctx):
    events = tmp_path / "events.jsonl"
    events.write_text(CODEX_EVENTS)
    binary = fake_cli(tmp_path, f'read -t 1 x && exit 9\ncat "{events}"\n')  # exits 9 if stdin is open
    h = codex(ctx, binary, sandbox="workspace-write", reasoning_effort="medium", model="gpt-x")
    reply = asyncio.run(h.reply("hi there", None))
    assert reply.say == "Hi Niklas, nice to meet you!"
    assert reply.session_id == "01a189d8-3ee8-7c13-bc63-bee05975fcea"
    assert reply.usage == Usage(18767, 0, 27)

    cwd, args = recorded(binary)
    assert Path(cwd).resolve() == ctx.home.resolve()
    schema = ctx.state_dir / "reply-schema.json"
    assert args[args.index("--output-schema") + 1] == str(schema)
    assert json.loads(schema.read_text())["required"] == ["emotion", "say"]
    assert 'model_reasoning_effort="medium"' in args and args[args.index("-m") + 1] == "gpt-x"
    assert args[-2:] == ["--", "hi there"]


def test_codex_adapter_resume_keeps_sandbox(tmp_path, ctx):
    events = tmp_path / "events.jsonl"
    events.write_text(CODEX_EVENTS)
    binary = fake_cli(tmp_path, f'cat "{events}"\n')
    asyncio.run(codex(ctx, binary, sandbox="danger-full-access").reply("again", "abc"))
    _, args = recorded(binary)
    assert args[:3] == ["exec", "resume", "abc"]
    assert 'sandbox_mode="danger-full-access"' in args


def test_codex_adapter_timeout(tmp_path, ctx):
    binary = fake_cli(tmp_path, "sleep 5\n")
    with pytest.raises(HarnessError, match="timed out") as e:
        asyncio.run(codex(ctx, binary, timeout_s=0.2).reply("hi", None))
    assert e.value.transient


def test_codex_adapter_nonzero_exit(tmp_path, ctx):
    binary = fake_cli(tmp_path, 'echo "Error: not logged in" >&2\nexit 1\n')
    with pytest.raises(HarnessError, match="not logged in"):
        asyncio.run(codex(ctx, binary).reply("hi", None))


def test_codex_adapter_turn_failed(tmp_path, ctx):
    binary = fake_cli(tmp_path, """echo '{"type":"turn.failed","error":{"message":"rate limited"}}'\n""")
    with pytest.raises(HarnessError, match="rate limited"):
        asyncio.run(codex(ctx, binary).reply("hi", None))


def test_missing_binary_is_a_harness_error(tmp_path, ctx):
    with pytest.raises(HarnessError, match="could not start") as e:
        asyncio.run(codex(ctx, str(tmp_path / "nope")).reply("hi", None))
    assert not e.value.transient


# ---- claude


def test_parse_claude_structured_output():
    reply = parse_result(CLAUDE_RESULT, 0, "", None)
    assert (reply.emotion, reply.say, reply.session_id) == (Emotion.EXCITED, "On it!", "s1")
    assert reply.usage == Usage(5030, 5000, 7)


def test_parse_claude_falls_back_to_result():
    out = json.dumps({"is_error": False, "result": '{"emotion":"sad","say":"Oh no."}', "session_id": "s2"})
    reply = parse_result(out, 0, "", None)
    assert (reply.emotion, reply.say, reply.session_id) == (Emotion.SAD, "Oh no.", "s2")


def test_parse_claude_error():
    with pytest.raises(HarnessError):
        parse_result(json.dumps({"is_error": True, "result": "overloaded"}), 1, "", None)
    with pytest.raises(HarnessError, match="boom"):
        parse_result("", 1, "boom", None)


def test_claude_resume_command(tmp_path):
    cmd = ClaudeHarness("claude", tmp_path, permission_mode="plan", model="opus").command("hi", "s1")
    assert cmd[cmd.index("--resume") + 1] == "s1"
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["required"] == ["emotion", "say"]
    assert cmd[-2:] == ["--", "hi"]
    assert os.path.basename(cmd[0]) == "claude"


def claude(ctx, binary: str, **options) -> ClaudeHarness:
    return HARNESSES.create("claude", {"binary": binary, **options}, ctx)


def test_claude_adapter_against_fake_binary(tmp_path, ctx):
    result = tmp_path / "result.json"
    result.write_text(CLAUDE_RESULT)
    binary = fake_cli(tmp_path, f'read -t 1 x && exit 9\ncat "{result}"\n')
    ctx.home.mkdir(parents=True)
    reply = asyncio.run(claude(ctx, binary).reply("hello", "s0"))
    assert (reply.say, reply.session_id) == ("On it!", "s1")
    cwd, args = recorded(binary)
    assert Path(cwd).resolve() == ctx.home.resolve()
    assert args[args.index("--resume") + 1] == "s0"
    assert args[args.index("--permission-mode") + 1] == "acceptEdits"
    assert args[-2:] == ["--", "hello"]


def test_claude_adapter_timeout(tmp_path, ctx):
    binary = fake_cli(tmp_path, "sleep 5\n")
    ctx.home.mkdir(parents=True)
    with pytest.raises(HarnessError, match="timed out"):
        asyncio.run(claude(ctx, binary, timeout_s=0.2).reply("hi", None))


def test_claude_adapter_nonzero_exit(tmp_path, ctx):
    binary = fake_cli(tmp_path, 'echo "Invalid API key" >&2\nexit 1\n')
    ctx.home.mkdir(parents=True)
    with pytest.raises(HarnessError, match="Invalid API key"):
        asyncio.run(claude(ctx, binary).reply("hi", None))


# ---- binary lookup


def test_find_binary_order(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(_binary.Path, "home", lambda: tmp_path)
    assert _binary.find_binary("/x/codex", "codex", section="harness.codex") == "/x/codex"

    bundled = tmp_path / "bundled" / "codex"
    bundled.parent.mkdir()
    bundled.write_text("")
    assert _binary.find_binary("", "codex-milo-test", (bundled,), section="harness.codex") == str(bundled)

    local = tmp_path / ".local" / "bin" / "codex-milo-test"
    local.parent.mkdir(parents=True)
    local.write_text("")
    assert _binary.find_binary("", "codex-milo-test", (bundled,), section="harness.codex") == str(local)

    on_path = tmp_path / "onpath"
    on_path.mkdir()
    fake_cli(on_path, "", name="codex-milo-test")
    monkeypatch.setenv("PATH", str(on_path))
    assert _binary.find_binary("", "codex-milo-test", (bundled,), section="harness.codex") == str(
        on_path / "codex-milo-test")


def test_find_binary_missing_names_the_section(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(_binary.Path, "home", lambda: tmp_path)
    with pytest.raises(ConfigError, match=r"\[harness.claude\]"):
        _binary.find_binary("", "claude-milo-test", section="harness.claude")


def test_claude_gets_milo_mac_as_an_allowed_mcp_server(tmp_path):
    mac_tools = ("/py", "-m", "milo.mcp_server", "--socket", "/s")
    cmd = ClaudeHarness("claude", tmp_path, mac_tools=mac_tools).command("hi", None)
    config = json.loads(cmd[cmd.index("--mcp-config") + 1])
    assert config == {"mcpServers": {"milo-mac": {"type": "stdio", "command": "/py",
                                                  "args": ["-m", "milo.mcp_server", "--socket", "/s"]}}}
    assert cmd[cmd.index("--allowedTools") + 1] == "mcp__milo-mac"
    assert cmd[-2:] == ["--", "hi"]
    assert "--mcp-config" not in ClaudeHarness("claude", tmp_path).command("hi", None)


def test_codex_gets_milo_mac_through_config_overrides(tmp_path):
    h = CodexHarness("codex", tmp_path, tmp_path / "s.json", mac_tools=("/py", "-m", "milo.mcp_server"))
    for cmd in (h.command("hi", None), h.command("again", "abc")):
        assert 'mcp_servers.milo-mac.command="/py"' in cmd
        assert 'mcp_servers.milo-mac.args=["-m", "milo.mcp_server"]' in cmd
        assert 'mcp_servers.milo-mac.default_tools_approval_mode="approve"' in cmd
