"""openai_compat against a fake chat completions server on localhost: what goes out, what streams back."""

import asyncio
import json

import pytest

from milo.adapters.harness.openai_compat import OpenAICompatModel, usage
from milo.core.ports import LiveModel
from milo.core.registry import LIVE_MODELS, AdapterContext, ConfigError
from milo.core.types import HarnessError, Usage

KEY = "sk-test-" + "k" * 40


class FakeServer:
    """Answers each POST with `replies[n]`: a list of SSE data payloads, or (status, body) for an error."""

    def __init__(self, *replies, chunked: bool = True, pause_s: float = 0.0):
        self.replies = list(replies)
        self.chunked = chunked
        self.pause_s = pause_s
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.closed = asyncio.Event()

    async def handle(self, reader, writer):
        head = (await reader.readuntil(b"\r\n\r\n")).decode().split("\r\n")
        assert head[0].startswith("POST /v1/chat/completions ")
        headers = {k.lower(): v for k, _, v in (line.partition(": ") for line in head[1:] if line)}
        self.headers.append(headers)
        self.requests.append(json.loads(await reader.readexactly(int(headers["content-length"]))))
        reply = self.replies.pop(0)
        try:
            if isinstance(reply, tuple):
                status, body = reply
                data = json.dumps(body).encode()
                writer.write(f"HTTP/1.1 {status} Nope\r\nContent-Type: application/json\r\n"
                             f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
                return
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                         + (b"Transfer-Encoding: chunked\r\n" if self.chunked else b"") + b"\r\n")
            for payload in [": keep-alive", *(f"data: {json.dumps(p)}" for p in reply), "data: [DONE]"]:
                event = (payload + "\n\n").encode()
                writer.write(f"{len(event):x}\r\n".encode() + event + b"\r\n" if self.chunked else event)
                await writer.drain()
                await asyncio.sleep(self.pause_s)
            if self.chunked:
                writer.write(b"0\r\n\r\n")
        except ConnectionError:
            pass
        finally:
            writer.close()
            self.closed.set()


def words(*texts, usage=None):
    chunks = [{"choices": [{"index": 0, "delta": {"content": t}}]} for t in texts]
    return chunks + ([{"choices": [], "usage": usage}] if usage else [])


async def started(fake):
    server = await asyncio.start_server(fake.handle, "127.0.0.1", 0)
    return server, f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/v1"


async def say(model, text, images=()):
    return "".join([d async for d in model.turn(text, images)])


def test_a_conversation_streams_keeps_its_history_and_reports_cached_tokens(tmp_path):
    fake = FakeServer(words("Hel", "lo!", usage={"prompt_tokens": 1200, "completion_tokens": 3,
                                                 "prompt_tokens_details": {"cached_tokens": 1024}}),
                      words("Fine."))
    key = tmp_path / "secrets" / "openai.key"
    key.parent.mkdir(mode=0o700)
    key.write_text(KEY)
    key.chmod(0o600)

    async def run():
        server, url = await started(fake)
        async with server:
            model = OpenAICompatModel(url, "gpt-test", key_file=key)
            await model.start("You are Milo.")
            assert await say(model, "hi") == "Hello!"
            assert model.last_usage == Usage(input_tokens=1200, cached_input_tokens=1024, output_tokens=3)
            assert await say(model, "how are you?") == "Fine."
            assert model.last_usage == Usage(), "a reply without usage reports none, not the turn before's"
            return model

    model = asyncio.run(run())
    assert isinstance(model, LiveModel)
    first, second = fake.requests
    assert fake.headers[0]["authorization"] == f"Bearer {KEY}" and fake.headers[0]["accept"] == "text/event-stream"
    assert first["model"] == "gpt-test" and first["stream"] is True and first["stream_options"] == {"include_usage": True}
    assert first["messages"] == [{"role": "system", "content": "You are Milo."}, {"role": "user", "content": "hi"}]
    assert second["messages"][:3] == [*first["messages"], {"role": "assistant", "content": "Hello!"}], \
        "the conversation only grows, so its start is the same and the provider's cache keeps hitting"
    assert first["prompt_cache_key"] == second["prompt_cache_key"].strip() != ""


def test_a_new_conversation_gets_a_new_cache_key_and_cache_control_marks_the_system_prompt():
    fake = FakeServer(words("a"), words("b"), chunked=False)

    async def run():
        server, url = await started(fake)
        async with server:
            model = OpenAICompatModel(url, "anthropic/claude-haiku-5-5", cache_control=True)
            await model.start("System.")
            await say(model, "one")
            await model.start("System.")
            await say(model, "two")

    asyncio.run(run())
    first, second = fake.requests
    assert first["prompt_cache_key"] != second["prompt_cache_key"]
    assert first["messages"][0] == {"role": "system", "content": [
        {"type": "text", "text": "System.", "cache_control": {"type": "ephemeral"}}]}
    assert "authorization" not in fake.headers[0], "a local server (Ollama, LM Studio) needs no key"


def test_a_screenshot_goes_along_as_a_data_url_unless_the_model_cant_see(tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG fake")
    fake = FakeServer(words("I see it."), words("ok"))

    async def run():
        server, url = await started(fake)
        async with server:
            await say(OpenAICompatModel(url, "m"), "what's this?", [png])
            await say(OpenAICompatModel(url, "m", images=False), "and this?", [png])

    asyncio.run(run())
    parts = fake.requests[0]["messages"][-1]["content"]
    assert parts[0] == {"type": "text", "text": "what's this?"}
    assert parts[1]["type"] == "image_url" and parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert fake.requests[1]["messages"][-1]["content"] == "and this?"


def test_interrupt_ends_the_reply_and_the_conversation_goes_on():
    fake = FakeServer(words(*[f"w{i} " for i in range(50)]), words("next"), pause_s=0.05)

    async def run():
        server, url = await started(fake)
        async with server:
            model = OpenAICompatModel(url, "m")
            got = []
            async for delta in model.turn("talk a lot"):
                got.append(delta)
                if len(got) == 2:
                    await model.interrupt()
            assert got[:2] == ["w0 ", "w1 "] and len(got) < 10
            await asyncio.wait_for(fake.closed.wait(), 2)
            assert await say(model, "go on") == "next"
            return model

    model = asyncio.run(run())
    assert fake.requests[1]["messages"][-2]["role"] == "assistant", "what was said before the stop stays"


def test_errors_say_what_the_provider_said_and_whether_a_retry_helps():
    fake = FakeServer((429, {"error": {"message": "Rate limit reached"}}), (401, {"error": {"message": "Bad key"}}),
                      words("fine"))

    async def run():
        server, url = await started(fake)
        async with server:
            model = OpenAICompatModel(url, "m")
            with pytest.raises(HarnessError, match="HTTP 429: Rate limit reached") as limited:
                await say(model, "one")
            assert limited.value.transient
            with pytest.raises(HarnessError, match="HTTP 401: Bad key") as refused:
                await say(model, "two")
            assert not refused.value.transient
            assert await say(model, "three") == "fine"
            gone = OpenAICompatModel("http://127.0.0.1:9/v1", "m", timeout_s=2)
            with pytest.raises(HarnessError, match="can't reach") as unreachable:
                await say(gone, "anyone?")
            assert unreachable.value.transient

    asyncio.run(run())
    assert fake.requests[2]["messages"] == [{"role": "user", "content": "three"}], "failed turns leave no trace"


def test_usage_reads_the_cached_tokens_each_provider_reports():
    assert usage({"prompt_tokens": 10, "completion_tokens": 2}) == Usage(10, 0, 2)
    assert usage({"prompt_tokens": 10, "prompt_cache_hit_tokens": 8, "completion_tokens": 2}) == Usage(10, 8, 2)
    assert usage({"prompt_tokens": 10, "prompt_tokens_details": None, "completion_tokens": 1}) == Usage(10, 0, 1)


def test_registered_with_the_key_in_secrets_and_a_model_it_must_name(tmp_path):
    ctx = AdapterContext(tmp_path, tmp_path / "state", clock=None)
    model = LIVE_MODELS.create("openai_compat", {"model": "llama3.2", "base_url": "http://localhost:11434/v1"}, ctx)
    assert model.url == "http://localhost:11434/v1/chat/completions" and model.key_file is None
    model = LIVE_MODELS.create("openai_compat", {"model": "gpt-x", "key_ref": "openai.key"}, ctx)
    assert model.key_file == tmp_path / "secrets" / "openai.key"
    with pytest.raises(ConfigError, match="needs model"):
        LIVE_MODELS.create("openai_compat", {}, ctx)
    with pytest.raises(ConfigError, match="base_url"):
        LIVE_MODELS.create("openai_compat", {"model": "m", "base_url": "localhost:1234"}, ctx)
    with pytest.raises(HarnessError, match="missing"):
        model._read_key()
