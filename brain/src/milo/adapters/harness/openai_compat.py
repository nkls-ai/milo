"""Any OpenAI-style chat completions API as Milo's live chat model: OpenAI, OpenRouter, Ollama, LM Studio, vLLM.

`[chat] use = "openai_compat"` with `[chat.openai_compat]` naming `base_url`, `model` and `key_ref` (a file in
~/Milo/secrets, read like every other key; empty for a local server that needs none).

Each turn POSTs the whole conversation to `<base_url>/chat/completions` with `stream: true` and reads the
server-sent events: `data: {"choices":[{"delta":{"content":"..."}}]}` lines, a last chunk with `usage` (asked
for with `stream_options.include_usage`) and `data: [DONE]`. The conversation lives here, as a list that only
grows, so its start is the same on every turn. That is what the providers' prompt caches key on:

- OpenAI caches a repeated prefix of 1024 tokens or more by itself; `prompt_cache_key` (one per conversation)
  keeps a conversation's requests on the same cache. Cached tokens come back as
  `usage.prompt_tokens_details.cached_tokens`.
- OpenRouter passes `prompt_cache_key` on, and with `cache_control = true` the system prompt carries an
  Anthropic-style `cache_control` breakpoint, which Claude and Gemini models through OpenRouter need.
- Ollama, LM Studio and llama.cpp reuse their KV cache for the same prefix and ignore the extra fields.

HTTP/1.1 on asyncio's own streams, one connection per turn, so interrupt() just closes it and nothing needs a
new dependency. No HTTP proxy support.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import ssl
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from milo.core.registry import LIVE_MODELS, AdapterContext, ConfigError, options_from
from milo.core.secrets import SecretError, read_secret
from milo.core.types import HarnessError, Usage

log = logging.getLogger(__name__)

MAX_LINE = 1024 * 1024  # one SSE line; a chunk is small, but an error body may not be
MAX_ERROR_BODY = 64 * 1024


@dataclass(frozen=True)
class OpenAICompatOptions:
    model: str = ""
    base_url: str = "https://api.openai.com/v1"
    """Up to and without /chat/completions: https://openrouter.ai/api/v1, http://localhost:11434/v1 (Ollama),
    http://localhost:1234/v1 (LM Studio)."""
    key_ref: str = ""
    """The key's file in ~/Milo/secrets ("openai.key"), or a path. Empty: no key (a local server)."""
    max_tokens: int = 600
    temperature: float = 0.7
    timeout_s: float = 30.0
    """Longest wait for the connection, the first byte, or the next piece of a reply."""
    cache_key: bool = True
    """Send `prompt_cache_key`, one per conversation (OpenAI, OpenRouter)."""
    cache_control: bool = False
    """Mark the system prompt with `cache_control` (Claude and Gemini models through OpenRouter)."""
    images: bool = True
    """Send screenshots along. Off for a model that can't see: the turn goes without them."""

    def __post_init__(self):
        if not self.model:
            raise ConfigError('[chat.openai_compat] needs model = "<the provider\'s model name>"')
        if urlsplit(self.base_url).scheme not in ("http", "https"):
            raise ConfigError("[chat.openai_compat] base_url must start with http:// or https://")


class OpenAICompatModel:
    """LiveModel over a chat completions endpoint that streams."""

    name = "openai_compat"

    def __init__(self, base_url: str, model: str, *, key_file: Path | None = None, max_tokens: int = 600,
                 temperature: float = 0.7, timeout_s: float = 30.0, cache_key: bool = True,
                 cache_control: bool = False, images: bool = True):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.key_file = key_file
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.cache_key = cache_key
        self.cache_control = cache_control
        self.images = images
        self.last_usage = Usage()
        self.messages: list[dict] = []
        self._conversation = ""
        self._key: str | None = None
        self._lock = asyncio.Lock()
        self._writer: asyncio.StreamWriter | None = None
        self._running = False
        self._interrupted = False

    async def start(self, system_prompt: str) -> None:
        """A new conversation. A reply still streaming stops; its turn finishes into the old one."""
        await self.interrupt()
        self._begin(system_prompt)

    def _begin(self, system_prompt: str) -> None:
        content: str | list[dict] = system_prompt
        if self.cache_control and system_prompt:
            content = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
        self.messages = [{"role": "system", "content": content}] if system_prompt else []
        self._conversation = uuid.uuid4().hex

    async def turn(self, text: str, images: Sequence[Path] = ()) -> AsyncIterator[str]:
        async with self._lock:
            if not self._conversation:
                self._begin("")
            # Reset first: an interrupted turn ends before its usage arrives and must not report the
            # previous turn's numbers a second time.
            self.last_usage = Usage()
            self._interrupted = False
            self._running = True
            messages = self.messages
            messages.append({"role": "user", "content": content(text, images if self.images else ())})
            said: list[str] = []
            try:
                async for delta in self._stream():
                    said.append(delta)
                    yield delta
            except (OSError, asyncio.IncompleteReadError, TimeoutError) as e:
                if not self._interrupted:
                    raise HarnessError(f"{self.name}: lost the connection to {self.url}: {e}",
                                       transient=True) from None
            finally:
                self._running = False
                self._writer = None
                if said:
                    # The reply so far stays in the conversation, as with claude_live: the next turn follows it.
                    messages.append({"role": "assistant", "content": "".join(said)})
                else:
                    messages.pop()  # nothing came back: as if the turn hadn't been sent, so roles still alternate

    async def interrupt(self) -> None:
        if not self._running or self._interrupted:
            return
        self._interrupted = True
        if self._writer is not None:
            self._writer.close()  # the reader sees the end at once; turn() ends quietly

    async def close(self) -> None:
        await self.interrupt()

    def request_body(self) -> dict:
        body: dict[str, Any] = {"model": self.model, "messages": self.messages, "stream": True,
                                "stream_options": {"include_usage": True}, "max_tokens": self.max_tokens,
                                "temperature": self.temperature}
        if self.cache_key:
            body["prompt_cache_key"] = f"milo-{self._conversation}"
        return body

    async def _stream(self) -> AsyncIterator[str]:
        url = urlsplit(self.url)
        port = url.port or (443 if url.scheme == "https" else 80)
        body = json.dumps(self.request_body(), ensure_ascii=False).encode()
        headers = {"Host": url.netloc, "Content-Type": "application/json", "Accept": "text/event-stream",
                   "Content-Length": str(len(body)), "Connection": "close", "User-Agent": "milo"}
        key = self._read_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            async with asyncio.timeout(self.timeout_s):
                reader, writer = await asyncio.open_connection(
                    url.hostname, port, ssl=ssl.create_default_context() if url.scheme == "https" else None,
                    limit=MAX_LINE)
        except (OSError, TimeoutError) as e:
            raise HarnessError(f"{self.name}: can't reach {url.netloc}: {e}", transient=True) from None
        self._writer = writer
        if self._interrupted:  # stopped while connecting
            writer.close()
            return
        try:
            path = (url.path or "/") + (f"?{url.query}" if url.query else "")
            writer.write(f"POST {path} HTTP/1.1\r\n".encode()
                         + "".join(f"{k}: {v}\r\n" for k, v in headers.items()).encode() + b"\r\n" + body)
            await writer.drain()
            async with asyncio.timeout(self.timeout_s):
                status, response = await _head(reader)
            lines = _lines(reader, response, self.timeout_s)
            if status >= 400:
                raise _http_error(self.name, status, await _text(lines))
            async for line in lines:
                if self._interrupted:
                    break
                if not line.startswith("data:"):
                    continue  # comments (": OPENROUTER PROCESSING"), event names, blank separators
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    log.warning("%s: skipping a line that isn't JSON: %r", self.name, data[:80])
                    continue
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("error"):
                    raise _http_error(self.name, 200, json.dumps(chunk))
                if isinstance(chunk.get("usage"), dict):
                    self.last_usage = usage(chunk["usage"])
                delta = _delta(chunk)
                if delta:
                    yield delta
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _read_key(self) -> str:
        if self.key_file is None:
            return ""
        if self._key is None:
            try:
                self._key = read_secret(self.key_file, f"The key for {self.url}")
            except SecretError as e:
                raise HarnessError(str(e), transient=False) from None
        return self._key


def content(text: str, images: Sequence[Path] = ()) -> str | list[dict]:
    """A user message's content: the plain text, or a text part followed by one image part per readable PNG."""
    parts: list[dict] = []
    for path in images:
        try:
            data = base64.b64encode(Path(path).read_bytes()).decode()
        except OSError as e:
            log.warning("openai_compat: leaving out an image: %s", e)
            continue
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}})
    return [{"type": "text", "text": text}, *parts] if parts else text


def usage(u: Mapping[str, Any]) -> Usage:
    """OpenAI's usage as Milo counts it: input_tokens includes the cached ones, as for Claude."""
    details = u.get("prompt_tokens_details") or {}
    cached = (details.get("cached_tokens") if isinstance(details, dict) else 0) or u.get("prompt_cache_hit_tokens", 0)
    return Usage(input_tokens=int(u.get("prompt_tokens", 0) or 0), cached_input_tokens=int(cached or 0),
                 output_tokens=int(u.get("completion_tokens", 0) or 0))


def _delta(chunk: dict) -> str:
    choices = chunk.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return ""
    text = (choices[0].get("delta") or {}).get("content")
    return text if isinstance(text, str) else ""


async def _head(reader: asyncio.StreamReader) -> tuple[int, dict[str, str]]:
    """The status code and the headers, names in lower case."""
    status_line = (await reader.readline()).decode("latin-1").split()
    if len(status_line) < 2 or not status_line[1].isdigit():
        raise OSError(f"not an HTTP answer: {' '.join(status_line)[:80]!r}")
    headers = {}
    while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
        name, _, value = line.decode("latin-1").partition(":")
        headers[name.strip().lower()] = value.strip()
    return int(status_line[1]), headers


async def _lines(reader: asyncio.StreamReader, headers: Mapping[str, str], timeout_s: float) -> AsyncIterator[str]:
    """The body's lines, decoded, with chunked transfer encoding taken apart."""
    async def body() -> AsyncIterator[bytes]:
        if "chunked" in headers.get("transfer-encoding", "").lower():
            while True:
                async with asyncio.timeout(timeout_s):
                    size = int((await reader.readline()).split(b";")[0].strip() or b"0", 16)
                    if size == 0:
                        return
                    data = await reader.readexactly(size)
                    await reader.readexactly(2)
                yield data
        else:
            left = int(headers["content-length"]) if headers.get("content-length", "").isdigit() else None
            while left is None or left > 0:
                async with asyncio.timeout(timeout_s):
                    data = await reader.read(65536 if left is None else min(65536, left))
                if not data:
                    return
                if left is not None:
                    left -= len(data)
                yield data

    pending = b""
    async for data in body():
        pending += data
        *done, pending = pending.split(b"\n")
        for line in done:
            yield line.rstrip(b"\r").decode("utf-8", errors="replace")
    if pending:
        yield pending.rstrip(b"\r").decode("utf-8", errors="replace")


async def _text(lines: AsyncIterator[str]) -> str:
    out, size = [], 0
    async for line in lines:
        out.append(line)
        size += len(line)
        if size > MAX_ERROR_BODY:
            break
    return "\n".join(out)


def _http_error(name: str, status: int, body: str) -> HarnessError:
    """The provider's own message where it gives one. Rate limits, overload and server errors are worth a retry;
    a bad key, model or request isn't."""
    message = body.strip()[:300]
    with contextlib.suppress(ValueError, AttributeError, TypeError):
        error = json.loads(body).get("error")
        message = str(error.get("message") if isinstance(error, dict) else error) or message
        if isinstance(error, dict) and isinstance(error.get("code"), int):
            status = error["code"]
    return HarnessError(f"{name}: HTTP {status}: {message}", transient=status in (408, 409, 429) or status >= 500)


@LIVE_MODELS.register("openai_compat")
def _openai_compat(options: Mapping[str, Any], ctx: AdapterContext) -> OpenAICompatModel:
    o = options_from(OpenAICompatOptions, options, "chat.openai_compat")
    key_file = None
    if o.key_ref:
        ref = Path(o.key_ref).expanduser()
        key_file = ref if ref.is_absolute() else ctx.home / "secrets" / ref
    return OpenAICompatModel(o.base_url, o.model, key_file=key_file, max_tokens=o.max_tokens,
                             temperature=o.temperature, timeout_s=o.timeout_s, cache_key=o.cache_key,
                             cache_control=o.cache_control, images=o.images)
