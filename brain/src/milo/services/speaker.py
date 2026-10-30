from __future__ import annotations

import asyncio
import logging
import re
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
        self._held = False
        self._fed: list[tuple[str, float, float]] = []  # each piece fed: text, loop time it starts and ends
        self._fillers: set[int] = set()  # indexes into _fed of interjected clips, which aren't part of the reply
        self._synthesizing: str | None = None
        self._synthesis_began = 0.0
        self._changed = asyncio.Event()
        self._shown_before = ""  # the bubble's text from before a hold
        self._all_text = ""
        self._first_text_at: float | None = None
        self.first_sound_at: float | None = None
        """Loop time the first audio was queued, for the turn's timing."""
        self.shown = ""
        """The text in the bubble so far: every piece whose audio has been fed."""

    @property
    def done(self) -> bool:
        if self._interrupted:
            return True
        return self._closed and not self._held and (self._worker is None or self._worker.done())

    @property
    def held(self) -> bool:
        return self._held

    @property
    def open(self) -> bool:
        """It still takes text: not finished and not interrupted."""
        return not self._closed

    @property
    def text(self) -> str:
        """Everything this utterance has been given so far, spoken or not."""
        return self._all_text

    def add(self, text: str) -> None:
        """Queue more text. The worker picks it up as soon as a piece is ready."""
        if self._closed or not text:
            return
        self._all_text += text
        if self._first_text_at is None:
            self._first_text_at = asyncio.get_running_loop().time()
        self._chunker.add(text)
        self._more.set()
        self._ensure_worker()

    async def finish(self) -> bool:
        """No more text is coming. Wait until everything played; False if it was interrupted."""
        if not self._closed:
            self._closed = True
            self._more.set()
            self._ensure_worker()
        while True:
            if self._interrupted:
                return False
            worker = self._worker
            if not self._held and (worker is None or worker.done()):
                break
            self._changed.clear()
            waiting = [asyncio.ensure_future(self._changed.wait())]
            if worker is not None and not worker.done():
                waiting.append(worker)
            await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            waiting[0].cancel()
        if worker is None:
            return True
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
        self._stop_audio()
        self._changed.set()

    def hold(self) -> None:
        """Go quiet now but keep the place: resume() goes on from the piece that was cut off.

        Text that arrives meanwhile is kept too. Used when the user starts talking: if they turn out to say
        nothing, Milo picks up where he was instead of having been cut off for good.
        """
        if self._interrupted or self._held:
            return
        self._held = True
        now = asyncio.get_running_loop().time()
        fed = [f for i, f in enumerate(self._fed) if i not in self._fillers]
        unheard = [_from_heard_part(text, (now - start) / max(1e-6, end - start)) if start < now else text
                   for text, start, end in fed if end > now]
        heard = [text for text, start, end in fed if end <= now]
        if self._synthesizing is not None:
            unheard.append(self._synthesizing)
        rest = self._chunker.flush_raw()
        self._chunker = SpeechChunker()
        self._chunker.add(" ".join([*unheard, rest]) if unheard else rest)
        self._stop_audio()
        self._fed, self._fillers, self._synthesizing = [], set(), None
        self._began, self._play_end, self._pause = False, 0.0, 0.0
        self.shown = " ".join([self._shown_before, *heard]).strip() if heard or self._shown_before else ""
        self._shown_before = self.shown
        self._changed.set()

    def resume(self) -> bool:
        """Go on after hold(). False if there was nothing held."""
        if not self._held or self._interrupted:
            return False
        self._held = False
        self._worker = None
        self._ensure_worker()
        self._changed.set()
        return True

    def interject(self, text: str, audio: Audio) -> bool:
        """Play a ready clip ("Hm.") now, ahead of the reply. Only before any of the reply has sounded and while
        not held; False otherwise. The clip isn't shown and isn't said again after a hold."""
        if self.done or self._held or self._fed:
            return False
        loop = asyncio.get_running_loop()
        self._begin(loop)
        self._fillers.add(len(self._fed))
        self._feed(audio, text, loop)
        self._sounded(audio, text)
        return True

    def ready_in(self) -> float:
        """Roughly how long until the next piece is ready to play: infinite while there is no text."""
        if self._synthesizing is None:
            return 0.0 if self._fed else float("inf")
        pace = self._speaker.pace
        expected = pace.overhead_s + pace.seconds_per_char * len(self._synthesizing)
        return max(0.0, expected - (asyncio.get_running_loop().time() - self._synthesis_began))

    def _begin(self, loop: asyncio.AbstractEventLoop) -> None:
        if not self._began:
            self._speaker.output.begin(self._speaker.voice.sample_rate, throttled_levels(self._speaker.ui, loop))
            self._began = True
        if not self._speaker.ui.speaking:
            self._speaker.ui.speaking = True
            self._speaker.ui.set_state(MiloState.SPEAKING)

    def _sounded(self, audio: Audio, piece: str) -> None:
        if self.first_sound_at is None:
            rate = self._speaker.voice.sample_rate
            self.first_sound_at = self._play_end - len(audio) / rate
            log.info("first sound %.2fs after the first text (%d chars, %.2fs of audio)%s",
                     self.first_sound_at - (self._first_text_at or self.first_sound_at), len(piece),
                     len(audio) / rate, ", a backchannel" if self._fillers else "")

    def _ensure_worker(self) -> None:
        if self._held or self._interrupted:
            return
        if (self._worker is None or self._worker.done()) and (not self._chunker.empty or
                                                              (self._closed and self._began)):
            self._worker = asyncio.create_task(self._play())

    def _stop_audio(self) -> None:
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
        if not self._began:
            speaker.output.begin(sample_rate, throttled_levels(ui, loop))
            self._began = True
        try:
            while (piece := await self._next_piece(loop)) is not None:
                started = self._synthesis_began = loop.time()
                self._synthesizing = piece
                audio = await self._synthesize(piece)
                self._synthesizing = None
                if audio is None:
                    audio = np.zeros(int(SECONDS_PER_CHAR_WITHOUT_AUDIO * len(piece) * sample_rate), np.float32)
                else:
                    speaker.pace.learn(len(piece), loop.time() - started)
                    audio = shape(audio, sample_rate)
                if not ui.speaking:
                    ui.speaking = True
                    ui.set_state(MiloState.SPEAKING)
                self._feed(audio, piece, loop)
                self._sounded(audio, piece)
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
        start = max(now, self._play_end)
        self._play_end = start + len(audio) / sample_rate
        self._fed.append((piece, start, self._play_end))
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


_BREAK = re.compile(r"(?<=[.!?…,;:–—])\s+")


def _from_heard_part(text: str, heard: float) -> str:
    """Where to pick up a piece that was cut off after `heard` (0..1) of it: the start of the sentence or clause
    that was playing, so Milo repeats a few words rather than starting mid-word or from the top of a long piece."""
    cut = int(len(text) * max(0.0, min(1.0, heard)))
    starts = [m.end() for m in _BREAK.finditer(text) if m.end() <= cut]
    return text[starts[-1]:] if starts else text


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
        self.held = False
        """hold() is in force: what is being said, and a reply that starts meanwhile, wait for resume()."""

    @property
    def active(self) -> bool:
        return self.current is not None and not self.current.done

    @property
    def recent_text(self) -> str:
        """What the current utterance has said and is about to say, to tell Milo's echo from the user."""
        u = self.current
        return "" if u is None else u.text

    def utterance(self, emotion: Emotion) -> Utterance:
        """Start speaking a reply whose text is still arriving. Interrupts whatever is being said."""
        held = self.held
        self.interrupt()
        self.ui.set_emotion(emotion)
        self.current = Utterance(self)
        if held:
            self.held = True
            self.current.hold()
        return self.current

    def hold(self) -> None:
        """Go quiet now, keeping the place in what is being said (see Utterance.hold)."""
        self.held = True
        self.ui.speaking = False
        if self.active:
            self.current.hold()

    def resume(self) -> bool:
        """Go on after hold(). False if nothing was waiting to be said."""
        held, self.held = self.held, False
        return held and self.current is not None and self.current.resume()

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
        self.held = False
        if self.active:
            self.ui.speaking = False
            self.current.interrupt()
