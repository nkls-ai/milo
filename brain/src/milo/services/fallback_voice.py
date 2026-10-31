from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

import numpy as np

from milo.core.ports import StreamingVoice, Voice, VoiceStream
from milo.core.types import Audio, VoiceUnavailable

log = logging.getLogger("milo.tts")

RETRY_S = 120.0
"""After a cloud voice failed, replies use the fallback for this long before the cloud voice gets another try."""

NOTICE = "I can't reach my usual voice right now, so I'm talking with my own for a while."


class FallbackVoice:
    """A Voice that swaps to a simpler engine when the configured one can't be used, so Milo still talks.

    An engine that fails to load is replaced for good. A cloud engine can also fail later: offline, a bad key,
    no credits. Then its stream or synthesize() raises VoiceUnavailable, and replies use the fallback until
    RETRY_S has passed. The fallback loads only then, on the TTS thread: a local voice holds gigabytes that a
    16 GB Mac shouldn't keep for a voice it may never need ("say" loads at once, OmniVoice takes a while).
    `on_switch(reason)` hears about each switch to the fallback, at most once per RETRY_S. Fallback audio comes
    resampled to the primary's rate, so an open output stream can go on.
    """

    def __init__(self, primary: Voice, fallback_factory: Callable[[], Voice] | None,
                 on_switch: Callable[[str], None] | None = None, clock: Callable[[], float] = time.monotonic):
        self._voice = primary
        self._primary = primary
        self._fallback_factory = fallback_factory
        self._fallback: Voice | None = None
        self.on_switch = on_switch
        self._clock = clock
        self._down_since: float | None = None
        self._told_at: float | None = None

    @property
    def current(self) -> Voice:
        """The engine speaking now."""
        return self._fallback if self._using_fallback() else self._voice

    @property
    def sample_rate(self) -> int:
        return self._voice.sample_rate

    @property
    def clip_key(self) -> str | None:
        """The main voice's clip key while it speaks; None while the fallback does, so its clips aren't kept."""
        return None if self._using_fallback() else getattr(self._voice, "clip_key", None)

    @property
    def first_audio_s(self) -> float:
        return getattr(self._voice, "first_audio_s", 0.0)

    def warm(self) -> None:
        try:
            self._voice.warm()
        except Exception as e:
            if self._fallback_factory is None:
                raise
            log.exception("tts engine %s failed to load, switching to the fallback", type(self._voice).__name__)
            self._voice = self._load_fallback()
            self._switched(str(e) or type(e).__name__)

    def synthesize(self, text: str) -> Audio:
        if not self._using_fallback():
            try:
                return self._voice.synthesize(text)
            except VoiceUnavailable as e:
                if self._fallback_factory is None:
                    raise
                self.failed(str(e))
        try:
            fallback = self._load_fallback()
        except Exception as e:
            raise VoiceUnavailable(f"the fallback voice failed to load: {e}") from e
        return _resample(fallback.synthesize(text), fallback.sample_rate, self.sample_rate)

    def cancel(self) -> None:
        self._voice.cancel()
        if self._fallback is not None and self._fallback is not self._voice:
            self._fallback.cancel()

    def stream(self) -> VoiceStream | None:
        if self._using_fallback() or not isinstance(self._voice, StreamingVoice):
            return None
        stream = self._voice.stream()
        return None if stream is None else _Watched(stream, self)

    def prepare(self) -> None:
        if not self._using_fallback() and isinstance(self._voice, StreamingVoice):
            self._voice.prepare()

    def failed(self, reason: str) -> None:
        """The cloud voice broke: use the fallback for a while (if there is one)."""
        if self._fallback_factory is None:
            log.warning("the voice failed and there is no fallback: %s", reason)
            return
        now = self._clock()
        if self._down_since is None or now - self._down_since >= RETRY_S:
            log.warning("the voice failed, using the fallback for %.0f s: %s", RETRY_S, reason)
        self._down_since = now
        self._switched(reason)

    def _using_fallback(self) -> bool:
        if self._down_since is None:
            return False
        if self._clock() - self._down_since >= RETRY_S:
            self._down_since = None
            log.info("trying the usual voice again")
            return False
        return True

    def _load_fallback(self) -> Voice:
        if self._fallback is None:
            fallback = self._fallback_factory()
            fallback.warm()
            self._fallback = fallback
        return self._fallback

    def _switched(self, reason: str) -> None:
        now = self._clock()
        if self.on_switch is not None and (self._told_at is None or now - self._told_at >= RETRY_S):
            self._told_at = now
            self.on_switch(reason)


class _Watched:
    """A stream whose failure switches the FallbackVoice over."""

    def __init__(self, stream: VoiceStream, voice: FallbackVoice):
        self._stream = stream
        self._voice = voice

    def send(self, text: str) -> None:
        self._stream.send(text)

    def finish(self) -> None:
        self._stream.finish()

    def cancel(self) -> None:
        self._stream.cancel()

    async def __aiter__(self) -> AsyncIterator[tuple[int, Audio]]:
        try:
            async for item in self._stream:
                yield item
        except VoiceUnavailable as e:
            self._voice.failed(str(e))
            raise


class VoiceNotice:
    """Says `text` (by default NOTICE) when called, after whatever Milo is saying now: the voice or the hearing
    switched to its local fallback. The callers call it at most once per switch, and it says it once per reason:
    a used-up quota fails the same way at every retry, and hearing it every few minutes helps nobody.

    It may be called from the TTS thread; the notice waits on the event loop (`loop`, set once it runs) until
    Milo is quiet."""

    def __init__(self, say: Callable[[str], object], busy: Callable[[], bool], wait_s: float = 60.0,
                 text: str = NOTICE):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.text = text
        self._say = say
        self._busy = busy
        self._wait_s = wait_s
        self._task: asyncio.Task | None = None
        self._told: set[str] = set()

    def __call__(self, reason: str) -> None:
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self._start, reason)

    def _start(self, reason: str) -> None:
        if reason in self._told:
            return
        self._told.add(reason)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._tell())

    async def _tell(self) -> None:
        from .quiet import wait_while

        if await wait_while(self._busy, self._wait_s):
            self._say(self.text)


def _resample(audio: Audio, rate: int, to: int) -> Audio:
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if rate == to or not len(audio):
        return audio
    n = int(round(len(audio) * to / rate))
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
