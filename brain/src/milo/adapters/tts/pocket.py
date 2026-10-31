"""Kyutai's Pocket TTS, a small local voice on the CPU. Needs the `pocket` extra; imported only on warm().

On an M3 it speaks about 7x faster than real time, its first audio after ~0.05 s, and a stream plays a piece
while it is still being made. Each model speaks one language: English and German both load at warm-up with the
same premade voice, and every piece goes to the model of its language (core/language.detect). A piece too short
to tell ("Okay.") keeps the language of the one before.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from milo.core.language import detect
from milo.core.registry import VOICES, AdapterContext, options_from
from milo.core.types import Audio, VoiceUnavailable

log = logging.getLogger(__name__)

WARM_UP_TEXT = "Okay."
_END = object()


class SynthesisCancelled(Exception):
    """cancel() stopped a synthesis between frames."""


@dataclass(frozen=True)
class PocketOptions:
    voice: str = "stuart_bell"  # one of Pocket's premade voices; they exist for every language model
    english: str = "english"  # the model for English pieces; "" for none
    german: str = "german"  # the model for German pieces; "" for none


class PocketTTS:
    sample_rate = 24_000
    first_audio_s = 0.1

    def __init__(self, *, voice: str = "stuart_bell", english: str = "english", german: str = "german"):
        self.voice = voice
        self.languages = {code: model for code, model in (("en", english), ("de", german)) if model}
        self._models: dict[str, tuple[Any, Any]] = {}  # language code: (model, voice state)
        self._last = next(iter(self.languages), "en")
        self._stops: set[threading.Event] = set()
        self._lock = threading.Lock()  # a Pocket model speaks one text at a time

    @property
    def clip_key(self) -> str:
        """See services/backchannel.py: rendered clips are kept per voice."""
        return f"pocket {self.voice} " + " ".join(f"{c}={m}" for c, m in self.languages.items())

    def warm(self) -> None:
        if self._models:
            return
        if not self.languages:
            raise RuntimeError("[tts.pocket] names no model: set english or german")
        try:
            from pocket_tts import TTSModel
        except ImportError as e:
            raise RuntimeError("Pocket TTS isn't installed: the brain needs the `pocket` extra") from e
        for code, language in self.languages.items():
            model = TTSModel.load_model(language=language)
            if model.sample_rate != self.sample_rate:
                raise RuntimeError(f"Pocket's {language} model speaks at {model.sample_rate} Hz, "
                                   f"not {self.sample_rate}")
            state = model.get_state_for_audio_prompt(self.voice)
            model.generate_audio(state, WARM_UP_TEXT)  # the first call is slow; let it be this one
            self._models[code] = (model, state)
        log.info("tts ready: Pocket TTS, voice %s, %s", self.voice, ", ".join(self.languages.values()))

    def synthesize(self, text: str) -> Audio:
        stop = threading.Event()
        self._stops.add(stop)
        try:
            chunks = list(self.render(text, stop))
        finally:
            self._stops.discard(stop)
        if stop.is_set():
            raise SynthesisCancelled("synthesis cancelled")
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

    def render(self, text: str, stop: threading.Event) -> Iterator[Audio]:
        """`text` as it is made, in the model of its language. Blocking; ends early once `stop` is set."""
        self.warm()
        code = detect(text) or self._last
        if code not in self._models:
            code = self._last if self._last in self._models else next(iter(self._models))
        self._last = code
        model, state = self._models[code]
        with self._lock:
            for chunk in model.generate_audio_stream(state, text, stop=stop):
                yield chunk.numpy().astype(np.float32)

    def cancel(self) -> None:
        for stop in list(self._stops):
            stop.set()

    # ---- StreamingVoice

    def stream(self) -> PocketStream | None:
        return PocketStream(self, asyncio.get_running_loop()) if self._models else None

    def prepare(self) -> None:
        pass  # nothing to open: the models are loaded


class PocketStream:
    """One reply: its pieces rendered in order on a thread of its own, each one's audio handed over as it comes,
    so the first words play ~0.1 s after the first piece instead of after all of it. See VoiceStream."""

    def __init__(self, voice: PocketTTS, loop: asyncio.AbstractEventLoop):
        self._voice = voice
        self._loop = loop
        self._pieces: queue.SimpleQueue[str | None] = queue.SimpleQueue()
        self._out: asyncio.Queue[object] = asyncio.Queue()
        self._stop = threading.Event()
        voice._stops.add(self._stop)  # cancel() on the voice (barge-in) stops this too
        threading.Thread(target=self._run, name="pocket-stream", daemon=True).start()

    def send(self, text: str) -> None:
        self._pieces.put(text)

    def finish(self) -> None:
        self._pieces.put(None)

    def cancel(self) -> None:
        self._stop.set()
        self._pieces.put(None)
        self._hand(_END)

    async def __aiter__(self) -> AsyncIterator[tuple[int, Audio]]:
        while True:
            item = await self._out.get()
            if item is _END or self._stop.is_set():
                return
            if isinstance(item, Exception):
                raise VoiceUnavailable(f"Pocket TTS failed: {item}") from item
            yield item

    def _run(self) -> None:
        try:
            index = 0
            while not self._stop.is_set() and (text := self._pieces.get()) is not None:
                for audio in self._voice.render(text, self._stop):
                    self._hand((index, audio))
                self._hand((index, np.zeros(0, dtype=np.float32)))
                index += 1
        except Exception as e:
            log.exception("Pocket TTS failed in the middle of a reply")
            self._hand(e)
        finally:
            self._voice._stops.discard(self._stop)
            self._hand(_END)

    def _hand(self, item: object) -> None:
        try:
            self._loop.call_soon_threadsafe(self._out.put_nowait, item)
        except RuntimeError:
            pass  # the loop is gone: Milo is shutting down


@VOICES.register("pocket")
def _pocket(options: Mapping[str, Any], ctx: AdapterContext) -> PocketTTS:
    o = options_from(PocketOptions, options, "tts.pocket")
    return PocketTTS(voice=o.voice, english=o.english, german=o.german)
