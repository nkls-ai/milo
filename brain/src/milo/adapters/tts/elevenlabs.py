"""ElevenLabs, a cloud voice that streams: the reply's text goes in while it is still being written, and the audio
comes back as one continuous delivery, so pitch and pace carry across sentences.

Speech goes over the multi-context WebSocket (`/v1/text-to-speech/{voice}/multi-stream-input`). One connection
stays open between replies; each reply is a context on it, and a cut-off reply only closes its context. Pieces
(whole sentences, see services/chunker.py) go in with `auto_mode`, which starts each one at once instead of
waiting for 120 characters to pile up. Audio comes back as 24 kHz PCM, nothing to decode. Each audio message
says which characters it speaks (`alignment`), which tells the speaker where one piece ends and the next begins.

Measured from Germany on 2026-10-30 (docs/research/voice.md): about 0.4 s from a sentence going in to its first
audio with eleven_flash_v2_5, a sentence of audio every few hundred ms after that, and the same pitch from
sentence to sentence (0.5 to 1.4 semitones of spread between phrases, like one whole-text render).

synthesize() renders a whole text over HTTP, for the short clips rendered at warm-up ("Hm.").

The API key is read from a file (`key_file`, by default ~/Milo/secrets/elevenlabs.key), never from config.toml,
and never logged. No voice is uploaded or cloned: `voice_id` names one of the account's voices.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import itertools
import json
import logging
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import numpy as np

from milo.core.secrets import SecretError, read_secret
from milo.core.registry import VOICES, AdapterContext, ConfigError, options_from
from milo.core.types import Audio, VoiceUnavailable

log = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
CONNECT_TIMEOUT_S = 5.0
NO_AUDIO_S = 5.0  # text went in and nothing came back for this long: the voice is gone
HTTP_TIMEOUT_S = 10.0
INACTIVITY_TIMEOUT_S = 180  # the server closes an idle connection after this (its maximum)
MIN_LIFE_S = 30.0  # a connection closed sooner than this isn't reopened by itself: something is wrong
KEEP_WARM_S = 600.0  # reopen a connection the server closed only if Milo spoke this recently
FIRST_AUDIO_GUESS_S = 0.45
DEFAULT_VOICE = "bIHbv24MWmeRgasZH58o"  # "Will", a premade voice: young, relaxed, conversational

_END = object()


@dataclass(frozen=True)
class ElevenLabsOptions:
    voice_id: str = DEFAULT_VOICE
    model: str = "eleven_flash_v2_5"  # the fastest; eleven_turbo_v2_5 is about as fast, eleven_multilingual_v2 slower
    key_file: str = ""  # empty: <workspace>/secrets/elevenlabs.key
    stability: float = 0.5
    similarity_boost: float = 0.75
    speed: float = 1.0
    language: str = ""  # empty: follows the text, which may switch between German and English
    server: str = "wss://api.elevenlabs.io"

    def __post_init__(self):
        if not self.voice_id.strip():
            raise ConfigError("[tts.elevenlabs] voice_id can't be empty")
        if not 0.7 <= self.speed <= 1.2:
            raise ConfigError("[tts.elevenlabs] speed must be between 0.7 and 1.2")
        for name in ("stability", "similarity_boost"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ConfigError(f"[tts.elevenlabs] {name} must be between 0 and 1")


class ElevenLabsVoice:
    """Voice and StreamingVoice. stream() and prepare() run on the event loop, synthesize() on the TTS thread."""

    sample_rate = SAMPLE_RATE

    def __init__(self, key_file: Path, voice_id: str = DEFAULT_VOICE, *, model: str = "eleven_flash_v2_5",
                 stability: float = 0.5, similarity_boost: float = 0.75, speed: float = 1.0, language: str = "",
                 server: str = "wss://api.elevenlabs.io", clock=None):
        self.key_file = key_file
        self.voice_id = voice_id
        self.model = model
        self.language = language
        self.server = server.rstrip("/")
        self.voice_settings = {"stability": stability, "similarity_boost": similarity_boost, "speed": speed}
        self.first_audio_s = FIRST_AUDIO_GUESS_S
        self._key: str | None = None
        self._connection: _Connection | None = None
        self._ids = itertools.count(1)
        self._last_used = -KEEP_WARM_S
        self._loop: asyncio.AbstractEventLoop | None = None

    # ---- Voice

    def warm(self) -> None:
        """Read the key. Raises VoiceUnavailable if there is none, so Milo falls back at once."""
        self._read_key()
        log.info("tts ready: ElevenLabs %s, voice %s", self.model, self.voice_id)

    def synthesize(self, text: str) -> Audio:
        """A whole text over HTTP. Blocking; raises VoiceUnavailable."""
        query = urlencode({"output_format": f"pcm_{SAMPLE_RATE}"})
        body = {"text": text, "model_id": self.model, "voice_settings": self.voice_settings}
        if self.language:
            body["language_code"] = self.language
        request = urllib.request.Request(
            f"{_http_base(self.server)}/v1/text-to-speech/{self.voice_id}?{query}", data=json.dumps(body).encode(),
            headers={"xi-api-key": self._read_key(), "content-type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
                pcm = response.read()
        except urllib.error.HTTPError as e:
            raise VoiceUnavailable(f"ElevenLabs said {e.code}: {_error_text(e)}") from None
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise VoiceUnavailable(f"ElevenLabs unreachable: {getattr(e, 'reason', e)}") from None
        return _samples(pcm[:len(pcm) // 2 * 2])

    def cancel(self) -> None:
        pass  # streams are cancelled one by one; an HTTP clip takes well under a second

    # ---- StreamingVoice

    def stream(self) -> ElevenLabsStream:
        self._loop = asyncio.get_running_loop()
        self._last_used = self._loop.time()
        return ElevenLabsStream(self, f"milo-{next(self._ids)}")

    def prepare(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
            self._connected()
        except Exception:
            log.debug("could not prepare the ElevenLabs connection", exc_info=True)

    async def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            await connection.close()

    # ---- internals

    def _read_key(self) -> str:
        if self._key is None:
            try:
                self._key = read_secret(self.key_file, "The ElevenLabs key",
                                        missing=f"no ElevenLabs key in {self.key_file}")
            except SecretError as e:
                raise VoiceUnavailable(str(e)) from None
        return self._key

    def _url(self) -> str:
        query = {"model_id": self.model, "output_format": f"pcm_{SAMPLE_RATE}", "auto_mode": "true",
                 "inactivity_timeout": INACTIVITY_TIMEOUT_S, "sync_alignment": "true"}
        if self.language:
            query["language_code"] = self.language
        return f"{self.server}/v1/text-to-speech/{self.voice_id}/multi-stream-input?{urlencode(query)}"

    def _connected(self) -> _Connection:
        """The open connection, or one that is opening now."""
        if self._connection is None or self._connection.closed:
            self._connection = _Connection(self, self._url(), self._read_key())
        return self._connection

    def _send(self, stream: ElevenLabsStream, message: dict) -> None:
        self._last_used = asyncio.get_running_loop().time()
        self._connected().send(stream, message)

    def _closed_idle(self, connection: _Connection) -> None:
        """The server closed a connection nobody was using. Reopen it if Milo spoke lately, so the next reply
        doesn't wait for a handshake."""
        if self._connection is connection:
            self._connection = None
            loop = self._loop
            now = loop.time() if loop is not None else 0.0
            if loop is not None and now - self._last_used < KEEP_WARM_S and now - connection.opened_at > MIN_LIFE_S:
                self._connected()

    def _learned(self, first_audio_s: float) -> None:
        self.first_audio_s = 0.7 * self.first_audio_s + 0.3 * first_audio_s


class _Connection:
    """One WebSocket: a writer sends messages in order, a reader hands audio to the stream it is for."""

    def __init__(self, voice: ElevenLabsVoice, url: str, key: str):
        self.voice = voice
        self.closed = False
        self.streams: dict[str, ElevenLabsStream] = {}
        self._outbox: asyncio.Queue[dict | None] = asyncio.Queue()
        self._ws = None
        self._closing = False
        self.opened_at = asyncio.get_running_loop().time()
        self._task = asyncio.create_task(self._run(url, key))

    def send(self, stream: ElevenLabsStream, message: dict) -> None:
        if self.closed:
            stream._fail("the ElevenLabs connection closed")
            return
        self.streams.setdefault(stream.context_id, stream)
        self._outbox.put_nowait(message)

    def forget(self, stream: ElevenLabsStream) -> None:
        self.streams.pop(stream.context_id, None)

    async def close(self) -> None:
        self.closed = self._closing = True
        self._outbox.put_nowait(None)
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task

    async def _run(self, url: str, key: str) -> None:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

        reason = "the ElevenLabs connection closed"
        idle = False
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT_S):
                self._ws = await connect(url, additional_headers={"xi-api-key": key}, max_size=16 * 2**20,
                                         open_timeout=None, ping_interval=20)
            writer = asyncio.create_task(self._write())
            try:
                async for raw in self._ws:
                    self._route(json.loads(raw))
                idle = not self.streams
            finally:
                writer.cancel()
            close = self._ws.close_reason or ""
            if close:
                reason = f"ElevenLabs closed the connection: {close}"
        except VoiceUnavailable as e:
            reason = str(e)
        except InvalidStatus as e:
            reason = f"ElevenLabs refused the connection ({e.response.status_code})"
        except ConnectionClosed as e:
            reason = f"ElevenLabs closed the connection: {e.rcvd.reason if e.rcvd else e}"
        except (TimeoutError, OSError, WebSocketException) as e:
            reason = f"ElevenLabs unreachable: {e or type(e).__name__}"
        except asyncio.CancelledError:
            reason = "the ElevenLabs connection was closed"
            self._closing = True
            raise
        finally:
            self.closed = True
            for stream in list(self.streams.values()):
                stream._fail(reason)
            self.streams.clear()
            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()
            if idle:
                log.info("ElevenLabs closed an idle connection")
                self.voice._closed_idle(self)
            elif not self._closing:
                log.warning("%s", reason)

    async def _write(self) -> None:
        while (message := await self._outbox.get()) is not None:
            await self._ws.send(json.dumps(message))

    def _route(self, message: dict) -> None:
        stream = self.streams.get(message.get("contextId") or "")
        if message.get("error") or (message.get("message") and "audio" not in message):
            text = message.get("message") or message.get("error")
            if stream is None:  # not about one reply: the connection is unusable
                raise VoiceUnavailable(f"ElevenLabs: {text}")
            stream._fail(f"ElevenLabs: {text}")
            return
        if stream is None:
            return  # audio for a context that was cancelled
        if message.get("audio"):
            stream._audio(base64.b64decode(message["audio"]), message.get("alignment"))
        if message.get("isFinal") or message.get("is_final"):
            stream._final()


class ElevenLabsStream:
    """One reply as one ElevenLabs context. See VoiceStream."""

    def __init__(self, voice: ElevenLabsVoice, context_id: str):
        self.voice = voice
        self.context_id = context_id
        self._queue: asyncio.Queue[object] = asyncio.Queue()
        self._ends: list[int] = []  # where each piece ends, counted in characters sent
        self._sent = 0
        self._spoken = 0  # characters the audio so far has covered
        self._piece = 0
        self._marked = -1
        self._started = False
        self._finished = False
        self._done = False
        self._odd = b""
        self._heard = False
        self._first_sent_at: float | None = None
        self._watchdog: asyncio.TimerHandle | None = None

    def send(self, text: str) -> None:
        text = " ".join(text.split())
        if not text or self._finished or self._done:
            return
        if not self._started:
            self._started = True
            self.voice._send(self, {"text": " ", "context_id": self.context_id,
                                    "voice_settings": self.voice.voice_settings})
        text += " "  # every message ends with a space, as the API asks
        self._sent += len(text)
        self._ends.append(self._sent)
        if self._first_sent_at is None:
            self._first_sent_at = asyncio.get_running_loop().time()
        self.voice._send(self, {"text": text, "context_id": self.context_id})
        self._arm()

    def finish(self) -> None:
        if self._finished or self._done:
            return
        self._finished = True
        if not self._started:
            self._end(_END)
            return
        self.voice._send(self, {"context_id": self.context_id, "flush": True})
        self.voice._send(self, {"context_id": self.context_id, "close_context": True})

    def cancel(self) -> None:
        if self._done:
            return
        self._close_context(again=True)  # also after finish(): the user cut it off, stop the audio now
        self._end(_END)

    async def __aiter__(self) -> AsyncIterator[tuple[int, Audio]]:
        while True:
            item = await self._queue.get()
            if item is _END:
                return
            if isinstance(item, VoiceUnavailable):
                raise item
            yield item

    # ---- from the connection

    def _audio(self, pcm: bytes, alignment: Mapping[str, Any] | None) -> None:
        if self._done:
            return
        if not self._heard:
            self._heard = True
            if self._first_sent_at is not None:
                self.voice._learned(asyncio.get_running_loop().time() - self._first_sent_at)
        pcm, self._odd = self._odd + pcm, b""
        if len(pcm) % 2:
            pcm, self._odd = pcm[:-1], pcm[-1:]
        samples = _samples(pcm)
        chars = (alignment or {}).get("chars") or ()
        starts = (alignment or {}).get("charStartTimesMs") or ()
        offset, last = self._spoken, len(self._ends) - 1
        self._spoken += len(chars)
        while self._piece < last and self._ends[self._piece] <= offset:
            self._complete(self._piece)
            self._piece += 1
        # Hand each piece its own samples: one message may end a piece and begin the next.
        cut = 0
        while self._piece < last and self._ends[self._piece] < self._spoken:
            i = self._ends[self._piece] - offset
            at = min(len(samples), max(cut, round(starts[i] * SAMPLE_RATE / 1000))) if i < len(starts) else cut
            if at > cut:
                self._queue.put_nowait((self._piece, samples[cut:at]))
            cut = at
            self._complete(self._piece)
            self._piece += 1
        if cut < len(samples):
            self._queue.put_nowait((self._piece, samples[cut:]))
        if self._ends and self._spoken >= self._ends[self._piece]:
            self._complete(self._piece)
        self._arm()

    def _complete(self, piece: int) -> None:
        """All of a piece's audio has come: say so with empty audio (see VoiceStream)."""
        if piece > self._marked:
            self._marked = piece
            self._queue.put_nowait((piece, _samples(b"")))

    def _final(self) -> None:
        self._end(_END)

    def _fail(self, reason: str) -> None:
        if not self._done:
            self._close_context()  # the server keeps only a few open; a stalled or failed one must not count
            self._end(VoiceUnavailable(reason))

    # ---- internals

    def _end(self, item: object) -> None:
        self._done = True
        if self._watchdog is not None:
            self._watchdog.cancel()
        connection = self.voice._connection
        if connection is not None:
            connection.forget(self)
        self._queue.put_nowait(item)

    def _arm(self) -> None:
        """Expect audio while text is still unspoken. Nothing for NO_AUDIO_S means the voice is gone."""
        if self._watchdog is not None:
            self._watchdog.cancel()
        self._watchdog = asyncio.get_running_loop().call_later(NO_AUDIO_S, self._stalled)

    def _stalled(self) -> None:
        if not self._done and self._sent - self._spoken > 1:
            self._fail(f"no audio from ElevenLabs for {NO_AUDIO_S:.0f} s")

    def _close_context(self, again: bool = False) -> None:
        """Tell the server this context is over, unless finish() did (`again`: even then) or there is no
        connection to tell."""
        connection = self.voice._connection
        if self._started and (again or not self._finished) and connection is not None and not connection.closed:
            connection.send(self, {"context_id": self.context_id, "close_context": True})


def _samples(pcm: bytes) -> Audio:
    return np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768


def _http_base(server: str) -> str:
    return "https://" + server.split("://", 1)[-1] if server.startswith("wss://") else \
        "http://" + server.split("://", 1)[-1]


def _error_text(e: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(e.read() or b"{}").get("detail")
    except (ValueError, OSError):
        return str(e.reason)
    if isinstance(detail, dict):
        return str(detail.get("message") or detail.get("status") or e.reason)
    return str(detail or e.reason)


@VOICES.register("elevenlabs")
def _elevenlabs(options: Mapping[str, Any], ctx: AdapterContext) -> ElevenLabsVoice:
    o = options_from(ElevenLabsOptions, options, "tts.elevenlabs")
    key_file = Path(o.key_file).expanduser() if o.key_file else ctx.home / "secrets" / "elevenlabs.key"
    return ElevenLabsVoice(key_file, o.voice_id, model=o.model, stability=o.stability,
                           similarity_boost=o.similarity_boost, speed=o.speed, language=o.language, server=o.server)
