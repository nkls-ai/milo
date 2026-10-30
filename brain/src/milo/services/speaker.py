from __future__ import annotations

import asyncio
import logging
from collections import deque
from concurrent.futures import Executor

import numpy as np

from milo.core.events import Bubble
from milo.core.logtext import private
from milo.core.ports import AudioOutput, Voice
from milo.core.types import Audio, Emotion, MiloState

from .chunker import SpeechChunker
from .levels import throttled_levels
from .speech_audio import END_PAD_S, pause_after, shape, silence
from .ui_state import UiState

log = logging.getLogger("milo.speaker")

SECONDS_PER_CHAR_WITHOUT_AUDIO = 0.06


class SynthesisPace:
    """How fast the voice synthesizes: a fixed cost per call plus a cost per character, fitted to recent pieces.

    budget() turns the audio still queued into the characters the voice can synthesize in that time. The
    starting guess is OmniVoice on an M3 at 6 steps, where each call also re-reads the 2 s voice reference;
    a least-squares fit over the last pieces replaces it once their lengths differ enough to tell the two apart.
    """

    def __init__(self, overhead_s: float = 1.0, seconds_per_char: float = 0.034, margin: float = 0.85,
                 window: int = 12):
        self.overhead_s = overhead_s
        self.seconds_per_char = seconds_per_char
        self.margin = margin
        self._samples: deque[tuple[int, float]] = deque(maxlen=window)

    def budget(self, ahead_s: float) -> int:
        return max(0, int((ahead_s * self.margin - self.overhead_s) / self.seconds_per_char))

    def learn(self, chars: int, took_s: float) -> None:
        self._samples.append((chars, took_s))
        n = len(self._samples)
        mean_c = sum(c for c, _ in self._samples) / n
        mean_t = sum(t for _, t in self._samples) / n
        var = sum((c - mean_c) ** 2 for c, _ in self._samples)
        if n >= 3 and var >= n * 15 ** 2:
            slope = sum((c - mean_c) * (t - mean_t) for c, t in self._samples) / var
            self.seconds_per_char = min(0.2, max(0.005, slope))
        self.overhead_s = min(3.0, max(0.0, mean_t - self.seconds_per_char * mean_c))


class Utterance:
    """One spoken reply, fed text while it is still being written. Plays piece after piece on one stream.

    A single worker cuts the next piece, synthesizes it on the TTS thread and feeds the audio to the output.
    feed() doesn't block, so the next piece synthesizes while this one plays. Each piece is sized from the
    audio still queued and the voice's measured speed, so it is ready before the queue runs dry.

    Each piece is trimmed to its speech and levelled (`speech_audio`), and the pause before the next one depends
    on how this one ended: a sentence pause after a full stop, a breath after a comma. Time the next piece spent
    synthesizing counts towards that pause, so a late piece doesn't add a pause on top of the wait.
    """

    def __init__(self, speaker: Speaker):
        self._speaker = speaker
        self._chunker = SpeechChunker()
        self._more = asyncio.Event()
        self._worker: asyncio.Task[bool] | None = None
        self._began = False
        self._closed = False
        self._interrupted = False
        self._play_end = 0.0  # loop time when the queued audio will have played
        self._pause = 0.0  # the pause the last piece asked for before the next
        self.shown = ""
        """The text in the bubble so far: every piece whose audio has been fed."""

    @property
    def done(self) -> bool:
        if self._interrupted:
            return True
        return self._closed and (self._worker is None or self._worker.done())

    def add(self, text: str) -> None:
        """Queue more text. The worker picks it up as soon as a piece is ready."""
        if self._closed or not text:
            return
        self._chunker.add(text)
        self._more.set()
        if self._worker is None and not self._chunker.empty:
            self._worker = asyncio.create_task(self._play())

    async def finish(self) -> bool:
        """No more text is coming. Wait until everything played; False if it was interrupted."""
        if not self._closed:
            self._closed = True
            self._more.set()
            if self._worker is None and not self._chunker.empty:
                self._worker = asyncio.create_task(self._play())
        if self._worker is None:
            return not self._interrupted
        await asyncio.wait({self._worker})
        worker = self._worker
        if worker.cancelled():
            return False
        if worker.exception() is not None:
            log.error("speech failed", exc_info=worker.exception())
            return False
        return worker.result()

    def interrupt(self) -> None:
        """Stop now: cut the audio and drop every piece not yet played."""
        if self._interrupted:
            return
        self._closed = self._interrupted = True
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
            self._speaker.voice.cancel()
        if self._began:
            self._speaker.output.interrupt()

    async def _next_piece(self, loop: asyncio.AbstractEventLoop) -> str | None:
        """Wait for text that makes a piece; None once everything has been taken."""
        while True:
            ahead = max(0.0, self._play_end - loop.time())
            piece = self._chunker.next(self._speaker.pace.budget(ahead), final=self._closed)
            if piece is not None or (self._closed and self._chunker.empty):
                return piece
            self._more.clear()
            await self._more.wait()

    async def _play(self) -> bool:
        speaker, ui = self._speaker, self._speaker.ui
        loop = asyncio.get_running_loop()
        sample_rate = speaker.voice.sample_rate
        speaker.output.begin(sample_rate, throttled_levels(ui, loop))
        self._began = True
        try:
            while (piece := await self._next_piece(loop)) is not None:
                started = loop.time()
                audio = await self._synthesize(piece)
                if audio is None:
                    audio = np.zeros(int(SECONDS_PER_CHAR_WITHOUT_AUDIO * len(piece) * sample_rate), np.float32)
                else:
                    speaker.pace.learn(len(piece), loop.time() - started)
                    audio = shape(audio, sample_rate)
                if not ui.speaking:
                    ui.speaking = True
                    ui.set_state(MiloState.SPEAKING)
                self._feed(audio, piece, loop)
                self.shown = f"{self.shown} {piece}".strip()
                ui.emit(Bubble(self.shown))
            if self._play_end:
                speaker.output.feed(silence(END_PAD_S, sample_rate))
            return await speaker.output.drain()
        finally:
            if speaker.current is self:
                ui.speaking = False
                if ui.state is MiloState.SPEAKING:
                    ui.rest()

    def _feed(self, audio: Audio, piece: str, loop: asyncio.AbstractEventLoop) -> None:
        """Queue a piece after the pause the previous one asked for, less the time already spent waiting."""
        sample_rate = self._speaker.voice.sample_rate
        now = loop.time()
        if self._play_end:
            waited = max(0.0, now - self._play_end)
            if waited > self._pause + 0.05:
                log.info("speech gap %.2fs before %s", waited - self._pause, private(piece[:40]))
            audio = np.concatenate([silence(self._pause - waited, sample_rate), audio])
        self._pause = pause_after(piece)
        self._play_end = max(now, self._play_end) + len(audio) / sample_rate
        self._speaker.output.feed(audio)

    async def _synthesize(self, chunk: str) -> Audio | None:
        speaker = self._speaker
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(speaker.executor, speaker.voice.synthesize, chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("tts failed; showing the text without audio")
            return None


class Speaker:
    """Speaks one utterance at a time; a new one cuts off the old. Shows the bubble as the audio goes out."""

    def __init__(self, voice: Voice, output: AudioOutput, sink: UiState, executor: Executor,
                 pace: SynthesisPace | None = None):
        self.voice = voice
        self.output = output
        self.ui = sink
        self.executor = executor
        self.pace = pace or SynthesisPace()
        self.current: Utterance | None = None

    @property
    def active(self) -> bool:
        return self.current is not None and not self.current.done

    def utterance(self, emotion: Emotion) -> Utterance:
        """Start speaking a reply whose text is still arriving. Interrupts whatever is being said."""
        self.interrupt()
        self.ui.set_emotion(emotion)
        self.current = Utterance(self)
        return self.current

    def say(self, text: str, emotion: Emotion, *, speak: bool = True) -> asyncio.Task[bool]:
        """Say a whole text, replacing whatever is being said.

        speak=False only shows the bubble and emotion, and leaves running speech alone: a silent nudge
        must not cut off Milo's answer.
        """
        if not speak or not text.strip():
            self.ui.set_emotion(emotion)
            self.ui.emit(Bubble(text))
            return asyncio.create_task(asyncio.sleep(0, True))
        utterance = self.utterance(emotion)
        utterance.add(text)
        return asyncio.create_task(utterance.finish())

    def interrupt(self) -> None:
        """Barge-in: stop the audio now and drop the rest. The caller decides which state to show next."""
        if self.active:
            self.ui.speaking = False
            self.current.interrupt()
