"""Transcription while the user is still speaking, so letting go of the key only waits for the last words.

A recording is cut into phrases at pauses. Each closed phrase is transcribed once with the full model
while the user goes on talking, and that text is final ("committed"). On release only the phrase still
open is left, and often not even that: when the user falls silent, the full model already transcribes
the open phrase as it stands (a "guess"), and if they let go before speaking again the guess is the end.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Executor
from dataclasses import dataclass
from functools import partial
from typing import NamedTuple

import numpy as np

from milo.core.events import Partial
from milo.core.logtext import private
from milo.core.ports import AudioInput, EventSink, Transcriber
from milo.core.types import STT_SAMPLE_RATE, Audio, Interrupted

log = logging.getLogger("milo.live_transcript")


class Cut(NamedTuple):
    """A phrase a pause closed, as sample indexes into the whole recording. `speech_end`: where its last
    speech frame ends."""

    start: int
    end: int
    speech_end: int


class PauseSegmenter:
    """Cuts a growing recording into phrases at pauses, by loudness alone.

    feed() takes the next samples and returns the phrases a pause closed (Cut). The cut lies in the middle of the pause, so both sides keep some silence.
    A phrase needs `min_speech_s` of speech; clicks and breaths alone never make one, and silence before
    speech is trimmed to `lead_s`. A phrase that has run for `long_s` closes at a shorter pause,
    `long_pause_s`, so a long dictation still comes in phrases of a few seconds. One longer than `max_s`
    without any pause is cut at its quietest frame, which keeps every pass inside one Whisper window.
    """

    def __init__(self, sample_rate: int = STT_SAMPLE_RATE, *, pause_s: float = 0.7, long_s: float = 6.0,
                 long_pause_s: float = 0.3, max_s: float = 12.0, min_speech_s: float = 0.2, lead_s: float = 0.3,
                 min_rms: float = 0.008, max_rms: float = 0.03, noise_ratio: float = 3.0, frame_s: float = 0.03):
        self._frame = int(sample_rate * frame_s)
        self._pause = max(2, round(pause_s / frame_s))
        self._long = round(long_s / frame_s)
        self._long_pause = max(2, round(long_pause_s / frame_s))
        self._max = round(max_s / frame_s)
        self._min_speech = max(1, round(min_speech_s / frame_s))
        self._lead = round(lead_s / frame_s)
        self._min_rms = min_rms
        self._max_rms = max_rms
        self._noise_ratio = noise_ratio
        self._noise: float | None = None  # quietest frame so far: the room's floor
        self._rest = np.zeros(0, dtype=np.float32)  # samples short of a whole frame
        self._levels: list[float] = []  # RMS of each frame of the open phrase
        self._open = 0  # frame where the open phrase starts
        self._speech = 0  # speech frames in the open phrase
        self._silence = 0  # silent frames at its end
        self._speech_end = 0  # frame after the last speech frame of the whole recording

    @property
    def open_start(self) -> int:
        """Sample index where the phrase not yet closed by a pause starts."""
        return self._open * self._frame

    @property
    def open_has_speech(self) -> bool:
        return self._speech >= self._min_speech

    @property
    def speech_end(self) -> int:
        """Sample index just after the last frame loud enough to be speech."""
        return self._speech_end * self._frame

    @property
    def silence_s(self) -> float:
        """How long the open phrase has been silent at its end."""
        return self._silence * self._frame / STT_SAMPLE_RATE

    def feed(self, samples: Audio) -> list[Cut]:
        data = np.concatenate([self._rest, np.asarray(samples, dtype=np.float32).reshape(-1)])
        n = len(data) // self._frame
        self._rest = data[n * self._frame:]
        if n == 0:
            return []
        frames = data[:n * self._frame].reshape(n, self._frame)
        levels = np.sqrt(np.mean(np.square(frames), axis=1))
        return [cut for level in levels.tolist() if (cut := self._step(level)) is not None]

    def _threshold(self) -> float:
        """A few times the room's floor, within limits: the floor is only known once there was a quiet
        frame, and speech from the very first frame must still count as speech."""
        return min(self._max_rms, max(self._min_rms, (self._noise or 0.0) * self._noise_ratio))

    def _step(self, level: float) -> Cut | None:
        if level > 1e-5:  # some mics deliver exact zeros while starting up
            self._noise = level if self._noise is None else min(self._noise, level)
        self._levels.append(level)
        if level >= self._threshold():
            self._speech += 1
            self._silence = 0
            self._speech_end = self._open + len(self._levels)
        else:
            self._silence += 1
        pause = self._long_pause if len(self._levels) - self._silence >= self._long else self._pause
        if self._silence >= pause:
            if self.open_has_speech:
                return self._cut(len(self._levels) - self._silence + pause // 2)
            self._speech = 0  # only a click or a breath: drop it with the silence
        if len(self._levels) >= self._max:
            if self.open_has_speech:
                half = len(self._levels) // 2
                return self._cut(half + int(np.argmin(self._levels[half:])))
            self._speech = 0
        if self._speech == 0 and len(self._levels) > self._lead:
            drop = len(self._levels) - self._lead
            self._open += drop
            del self._levels[:drop]
        return None

    def _cut(self, at: int) -> Cut:
        """Close the open phrase `at` frames in; the frames after it open the next one."""
        start = self.open_start
        speech_end = min(self.speech_end, (self._open + at) * self._frame)
        self._open += at
        self._levels = self._levels[at:]
        threshold = self._threshold()
        self._speech = sum(level >= threshold for level in self._levels)
        self._silence = 0
        for level in reversed(self._levels):
            if level >= threshold:
                break
            self._silence += 1
        return Cut(start, self.open_start, speech_end)


def join_phrases(texts: Iterable[str]) -> str:
    """Phrases transcribed one by one, as one text. Whisper ends every phrase with a full stop; when the
    next one goes on in lower case, the sentence went on, so that stop goes."""
    out = ""
    for text in (t.strip() for t in texts):
        if not text:
            continue
        if out and text[0].islower() and out.endswith(".") and not out.endswith(".."):
            out = out[:-1]
        out = f"{out} {text}" if out else text
    return out


@dataclass
class _Guess:
    """The full model's text for the open phrase from `start` to `end`, taken when it fell silent."""

    start: int
    end: int
    text: str


class LiveTranscript:
    """Transcribes one recording while it runs, on the STT executor, one pass at a time.

    Every `poll_s` it reads the new audio and lets the segmenter close phrases at pauses. Then it runs the
    most urgent pass, if any:

    1. Commit a closed phrase with the full model, at full accuracy. `on_phrase` gets each committed
       phrase in order (stream = "type" pastes it).
    2. Guess: the open phrase has been silent for `settle_s`, so the full model transcribes it as it is, in
       a quick pass. If the user speaks again, the guess is dropped. If they let go first, it is the end.
    3. Preview the open phrase with the fast model, once `min_new_s` more audio came in.

    `show` sends the words so far as a Partial: committed text, then the guess or preview of the open
    phrase. Commits and guesses always run before previews and start as soon as they are due, so the full
    model is never behind by more than one preview pass (about 0.05 s). A preview needs `gap_s` of idle
    GPU before it, which leaves room for speech synthesis, and none starts once the open phrase has gone
    quiet: the guess is about to come.

    finish() is the release: it interrupts a commit or preview in flight (a guess is let finish, it may be the
    end), commits what is left in quick passes and returns the whole text.
    """

    def __init__(self, mic: AudioInput, stt: Transcriber, executor: Executor, sink: EventSink,
                 segmenter: PauseSegmenter, *, on_phrase: Callable[[str], object] | None = None,
                 show: bool = True, poll_s: float = 0.1, gap_s: float = 0.15, settle_s: float = 0.25,
                 min_new_s: float = 0.5, monotonic: Callable[[], float] = time.monotonic):
        self._mic = mic
        self._stt = stt
        self._executor = executor
        self._sink = sink
        self._segmenter = segmenter
        self._on_phrase = on_phrase
        self._show_live = show
        self._poll_s = poll_s
        self._gap_s = gap_s
        self._settle_s = settle_s
        self._min_new = int(min_new_s * STT_SAMPLE_RATE)
        self._monotonic = monotonic
        self._heard = 0  # samples fed to the segmenter
        self._pending: list[Cut] = []  # closed phrases not yet committed
        self.phrases: list[str] = []  # committed text, one entry per phrase
        self._guess: _Guess | None = None
        self._preview = ""  # the fast model's text for the open phrase
        self._previewed = 0
        self._shown = ""
        self._passing = False
        self._interruptible = False
        self._idle_since = float("-inf")  # when the last pass ended
        self._closing = False
        self._task: asyncio.Task | None = None

    @property
    def text(self) -> str:
        return join_phrases(self.phrases)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def finish(self, audio: Audio) -> str:
        """The rest of `audio` (the whole recording) transcribed after the phrases already committed.
        Returns all of it. Everything left runs in quick passes: the user is waiting now."""
        await self._stop()
        self._listen(audio[self._heard:])
        if self._heard_nothing():
            # The segmenter heard no speech at all; maybe the voice was very quiet. One pass over everything.
            self._commit(await self._pass(self._stt.transcribe, audio, "", quick=True))
            return self.text
        while self._pending:
            await self._commit_next(lambda start, end: audio[start:end], quick=True)
        seg = self._segmenter
        if seg.open_has_speech:
            guess, self._guess, self._preview = self._guess, None, ""
            if guess is not None and guess.start == seg.open_start and seg.speech_end <= guess.end:
                log.debug("release: the guess covers the last phrase")
                self._commit(guess.text)
            else:
                self._commit(await self._pass(self._stt.transcribe, audio[seg.open_start:], self.text, quick=True))
        return self.text

    def abort(self) -> None:
        """Drop everything, e.g. on cancel."""
        self._closing = True
        if self._task is not None:
            self._task.cancel()

    async def _stop(self) -> None:
        self._closing = True
        task = self._task
        if task is None:
            return
        if not self._passing:
            task.cancel()
        elif self._interruptible:
            self._stt.interrupt()
        await asyncio.wait({task})

    async def _run(self) -> None:
        try:
            while not self._closing:
                await asyncio.sleep(self._poll_s)
                self._listen(self._mic.peek(self._heard))
                await self._next_pass()
        except asyncio.CancelledError:
            raise
        except Interrupted:
            log.debug("live pass interrupted by the release")
        except Exception:
            log.exception("live transcription failed; the rest is transcribed on release")

    def _listen(self, new: Audio) -> None:
        self._heard += len(new)
        self._pending.extend(self._segmenter.feed(new))
        guess = self._guess
        if guess is not None:
            closed = next((cut for cut in self._pending if cut.start == guess.start), None)
            if (closed.speech_end if closed is not None else self._segmenter.speech_end) > guess.end:
                self._guess = None  # the user went on talking

    async def _next_pass(self) -> None:
        """Run the most urgent pass, if any."""
        seg = self._segmenter
        if self._pending:
            await self._commit_next(lambda start, end: self._mic.peek(start)[:end - start], quick=False)
        elif seg.open_has_speech and seg.silence_s >= self._settle_s and self._guess is None:
            start, end = seg.open_start, self._heard
            text = await self._pass(self._stt.transcribe, self._mic.peek(start)[:end - start], self.text,
                                    quick=True, interruptible=False)
            if seg.open_start == start and seg.speech_end <= end:  # kept on release too: it may be the end
                self._guess = _Guess(start, end, text)
                self._show()
        elif (seg.open_has_speech and self._show_live and self._heard - self._previewed >= self._min_new
              and seg.silence_s < self._settle_s / 2 and self._monotonic() - self._idle_since >= self._gap_s):
            self._previewed = self._heard
            start = seg.open_start
            text = await self._pass(self._stt.preview, self._mic.peek(start), None)
            if not self._closing and seg.open_start == start:
                self._preview = text
                self._show()

    async def _commit_next(self, clip: Callable[[int, int], Audio], *, quick: bool) -> None:
        """Commit the oldest closed phrase; `clip(start, end)` gives its audio. A quick commit takes a guess
        still standing for the same phrase as its text: nothing was said after it. A full one does the
        phrase again at full accuracy."""
        start, end, _ = self._pending[0]
        guess = self._guess
        if quick and guess is not None and guess.start == start:
            text = guess.text
        else:
            text = await self._pass(self._stt.transcribe, clip(start, end), self.text, quick=quick)
        self._pending.pop(0)
        if self._guess is not None and self._guess.start == start:
            self._guess = None
        self._preview = ""
        self._commit(text)

    def _commit(self, text: str) -> None:
        text = text.strip()
        if text:
            self.phrases.append(text)
            if self._on_phrase is not None:
                self._on_phrase(text)
        self._show()

    def _heard_nothing(self) -> bool:
        return not self.phrases and not self._pending and not self._segmenter.open_has_speech

    async def _pass(self, fn: Callable[..., str], audio: Audio, before: str | None, *, quick: bool = False,
                    interruptible: bool = True) -> str:
        """Run `fn` on the STT executor. `before` None: a preview (no context, always quick)."""
        started = self._monotonic()
        self._passing = True
        self._interruptible = interruptible
        try:
            if before is None:
                text = await asyncio.get_running_loop().run_in_executor(self._executor, fn, audio)
            else:
                text = await asyncio.get_running_loop().run_in_executor(
                    self._executor, partial(fn, audio, before, quick=quick))
        finally:
            self._passing = False
            self._idle_since = self._monotonic()
        log.debug("%s %.1fs audio in %.2fs: %s", getattr(fn, "__name__", "pass"), len(audio) / STT_SAMPLE_RATE,
                  self._monotonic() - started, private(text))
        return text.strip()

    def _show(self) -> None:
        if not self._show_live:
            return
        guess = self._guess
        open_text = guess.text if guess is not None else self._preview
        parts = [open_text] if self._on_phrase is not None else [*self.phrases, open_text]
        text = join_phrases(parts)
        if text != self._shown:
            self._shown = text
            self._sink.emit(Partial(text))

