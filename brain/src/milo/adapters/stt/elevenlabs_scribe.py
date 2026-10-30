"""ElevenLabs Scribe v2 Realtime: the talk key's recording streams to ElevenLabs while the user speaks, and the
text is final about 0.2 s after they let go.

One WebSocket per recording (`/v1/speech-to-text/realtime`), opened when the recording starts, so the handshake
hides behind the user's words. Audio goes in as 16 kHz PCM in chunks of at most a second; letting go sends a
manual commit, and the `committed_transcript` that answers it is the text. Measured from Germany on 2026-10-30
(docs/research/voice.md): 0.18 to 0.27 s from the commit to the text, German and English mixed in one sentence
transcribed word for word, silence answered with "" in 0.2 s.

Only used where config.toml says audio may leave the Mac (`[stt] talk`). The key is read from a file and never
logged.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np

from milo.core.secrets import SecretError, read_secret
from milo.core.registry import STREAMING_TRANSCRIBERS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio, VoiceUnavailable

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_S = 5.0
FINAL_TIMEOUT_S = 3.0  # from the commit to the text; longer means the service is struggling: transcribe locally
MAX_CHUNK = STT_SAMPLE_RATE * 2  # bytes in one message: a second of audio, the most the service takes
LONG_S = 30.0  # past this much audio the service may have committed by itself (at ~36 s): wait for stragglers
STRAGGLER_S = 0.3

MAX_KEYTERMS = 50  # learned words are added to the configured keyterms up to this many
MAX_KEYTERM_CHARS = 50

_COMMIT = object()


@dataclass(frozen=True)
class ScribeOptions:
    key_file: str = ""  # empty: <workspace>/secrets/elevenlabs.key
    languages: tuple[str, ...] = ("de", "en")  # what you speak; helps it tell the languages apart. Empty: any
    keyterms: tuple[str, ...] = ()  # names it should get right (costs a little more)
    server: str = "wss://api.elevenlabs.io"


class ScribeRealtime:
    """StreamingTranscriber over ElevenLabs Scribe v2 Realtime."""

    def __init__(self, key_file: Path, *, languages: tuple[str, ...] = ("de", "en"), keyterms: tuple[str, ...] = (),
                 server: str = "wss://api.elevenlabs.io"):
        self.key_file = key_file
        self.languages = languages
        self.configured = keyterms
        self.keyterms = keyterms
        self.server = server.rstrip("/")
        self._key: str | None = None

    def use_vocabulary(self, words: Sequence[str]) -> None:
        """Vocabulary: the dictionary's words join `keyterms` from the next session on, up to MAX_KEYTERMS."""
        terms = list(dict.fromkeys(" ".join(w.split()) for w in (*self.configured, *words)))
        self.keyterms = tuple(t for t in terms if t and len(t) <= MAX_KEYTERM_CHARS)[:MAX_KEYTERMS]

    def session(self, on_partial: Callable[[str], None] | None = None) -> ScribeSession:
        try:
            key = self._read_key()
        except VoiceUnavailable as e:
            return ScribeSession.failed(str(e))
        return ScribeSession(self._url(), key, on_partial)

    def _read_key(self) -> str:
        if self._key is None:
            try:
                self._key = read_secret(self.key_file, "The ElevenLabs key",
                                        missing=f"no ElevenLabs key in {self.key_file}")
            except SecretError as e:
                raise VoiceUnavailable(str(e)) from None
        return self._key

    def _url(self) -> str:
        query: list[tuple[str, str]] = [("model_id", "scribe_v2_realtime"), ("audio_format", f"pcm_{STT_SAMPLE_RATE}"),
                                        ("commit_strategy", "manual")]
        query += [("secondary_languages", lang) for lang in self.languages]
        query += [("keyterms", term) for term in self.keyterms]
        return f"{self.server}/v1/speech-to-text/realtime?{urlencode(query)}"


class ScribeSession:
    """One recording. feed() queues audio; a task connects, sends it in order, and collects the committed text."""

    def __init__(self, url: str | None, key: str = "", on_partial: Callable[[str], None] | None = None):
        self._on_partial = on_partial
        self._outbox: asyncio.Queue[object] = asyncio.Queue()
        self._texts: list[str] = []
        self._final = asyncio.Event()
        self._error: str | None = None
        self._committed = False
        self._seconds = 0.0
        self._task = asyncio.create_task(self._run(url, key)) if url is not None else None

    @classmethod
    def failed(cls, reason: str) -> ScribeSession:
        session = cls(None)
        session._fail(reason)
        return session

    def feed(self, audio: Audio) -> None:
        samples = np.asarray(audio, dtype=np.float32).reshape(-1)
        if not len(samples) or self._committed:
            return
        self._seconds += len(samples) / STT_SAMPLE_RATE
        self._outbox.put_nowait((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())

    async def finish(self) -> str:
        if not self._committed:
            self._committed = True
            self._outbox.put_nowait(_COMMIT)
        try:
            async with asyncio.timeout(FINAL_TIMEOUT_S):
                await self._final.wait()
                if self._error is None and self._seconds > LONG_S:
                    await asyncio.sleep(STRAGGLER_S)
        except TimeoutError:
            self._fail(f"no text from ElevenLabs within {FINAL_TIMEOUT_S:.0f} s")
        finally:
            self.cancel()
        if self._error is not None:
            raise VoiceUnavailable(self._error)
        return " ".join(t for t in self._texts if t).strip()

    def cancel(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    def _fail(self, reason: str) -> None:
        if self._error is None:
            self._error = reason
        self._final.set()

    async def _run(self, url: str, key: str) -> None:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

        ws = None
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_S):
                ws = await connect(url, additional_headers={"xi-api-key": key}, open_timeout=None)
            reader = asyncio.create_task(self._read(ws))
            try:
                await self._write(ws)
                await reader
            finally:
                reader.cancel()
        except InvalidStatus as e:
            self._fail(f"ElevenLabs refused the connection ({e.response.status_code})")
        except ConnectionClosed as e:
            self._fail(f"ElevenLabs closed the connection: {e.rcvd.reason if e.rcvd else e}")
        except (TimeoutError, OSError, WebSocketException) as e:
            self._fail(f"ElevenLabs unreachable: {e or type(e).__name__}")
        finally:
            if ws is not None:
                with contextlib.suppress(Exception):
                    await ws.close()
            if not self._final.is_set():
                self._fail("the ElevenLabs connection closed")

    async def _write(self, ws) -> None:
        pending = b""
        while True:
            item = await self._outbox.get()
            if item is not _COMMIT:
                pending += item
                while not self._outbox.empty() and len(pending) < MAX_CHUNK:  # catch up after the handshake
                    nxt = self._outbox.get_nowait()
                    if nxt is _COMMIT:
                        self._outbox.put_nowait(_COMMIT)  # handled below, after the audio
                        break
                    pending += nxt
            while pending:
                chunk, pending = pending[:MAX_CHUNK], pending[MAX_CHUNK:]
                await ws.send(_chunk(chunk))
            if item is _COMMIT:
                await ws.send(_chunk(b"", commit=True))
                return

    async def _read(self, ws) -> None:
        async for raw in ws:
            message = json.loads(raw)
            kind = message.get("message_type", "")
            if kind == "partial_transcript" and self._on_partial is not None and not self._committed:
                self._on_partial(" ".join(t for t in [*self._texts, str(message.get("text", "")).strip()] if t))
            elif kind == "committed_transcript":
                self._texts.append(str(message.get("text", "")).strip())
                if self._committed:
                    self._final.set()
            elif "error" in message or kind.endswith("error"):
                self._fail(f"ElevenLabs: {message.get('error') or message.get('message') or kind}")
                return


def _chunk(pcm: bytes, *, commit: bool = False) -> str:
    return json.dumps({"message_type": "input_audio_chunk", "audio_base_64": base64.b64encode(pcm).decode(),
                       "commit": commit, "sample_rate": STT_SAMPLE_RATE})


@STREAMING_TRANSCRIBERS.register("elevenlabs")
def _scribe(options: Mapping[str, Any], ctx: AdapterContext) -> ScribeRealtime:
    o = options_from(ScribeOptions, options, "stt.elevenlabs")
    key_file = Path(o.key_file).expanduser() if o.key_file else ctx.home / "secrets" / "elevenlabs.key"
    return ScribeRealtime(key_file, languages=o.languages, keyterms=o.keyterms, server=o.server)
