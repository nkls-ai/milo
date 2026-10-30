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
from typing import NamedTuple

import numpy as np

from milo.core.events import Partial
from milo.core.logtext import private
from milo.core.ports import AudioInput, EventSink, Transcriber
from milo.core.types import STT_SAMPLE_RATE, Audio, Interrupted

log = logging.getLogger("milo.live_transcript")

QUIET_MIN_RMS = 0.002
QUIET_NOISE_RATIO = 2.5
"""A frame might hold a voice from 2.5 times the room's floor (but at least QUIET_MIN_RMS), well below the
speech threshold. A false alarm costs one more pass; missing a soft word loses it."""
MIN_VOICED_FRAMES = 2
MIN_WORDS_PER_S = 1.5
"""The safety net's line. Test dictations had 3.5 to 7 words per second of speech the segmenter heard."""
QUIET_RUN = 3  # frames: a pause needs at least this much true quiet to be cut in
LEAD_S = 0.3


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

    The speech threshold is made for finding pauses, not for deciding what holds words: a soft voice can
    stay below it. `voiced()` is the lenient check for that, a little above the room's floor.
    """

    def __init__(self, sample_rate: int = STT_SAMPLE_RATE, *, pause_s: float = 0.7, long_s: float = 6.0,
                 long_pause_s: float = 0.3, max_s: float = 12.0, min_speech_s: float = 0.2, lead_s: float = 0.3,
                 min_rms: float = 0.004, max_rms: float = 0.03, noise_ratio: float = 2.5, frame_s: float = 0.03):
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
        self._speech_total = 0  # speech frames in the whole recording

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
    def speech_s(self) -> float:
        """Seconds of speech in the whole recording so far."""
        return self._speech_total * self._frame / STT_SAMPLE_RATE

    @property
    def frame(self) -> int:
        return self._frame

    def voiced(self, audio: Audio) -> np.ndarray:
        """For each whole frame of `audio`: might it hold a voice? Lenient: anything clearly above the room."""
        n = len(audio) // self._frame
        if n == 0:
            return np.zeros(0, dtype=bool)
        frames = np.asarray(audio[:n * self._frame], dtype=np.float32).reshape(n, self._frame)
        return np.sqrt(np.mean(np.square(frames), axis=1)) >= self._quiet()

    def _quiet(self) -> float:
        noise = self._noise or 0.0
        # Well below the speech threshold, but above the room even where that threshold is near the floor.
        # Never above it: with no quiet frame yet, the "floor" is the voice itself.
        threshold = self._threshold()
        return min(threshold, max(QUIET_MIN_RMS, noise * 1.3, min(threshold * 0.6, noise * QUIET_NOISE_RATIO)))

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
            self._speech_total += 1
            self._silence = 0
            self._speech_end = self._open + len(self._levels)
        else:
            self._silence += 1
        pause = self._long_pause if len(self._levels) - self._silence >= self._long else self._pause
        if self._silence >= pause:
            if not self.open_has_speech:
                self._speech = 0  # only a click or a breath: drop it with the silence
            elif (at := self._quiet_middle(len(self._levels) - self._silence)) is not None:
                return self._cut(at)
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

    def _quiet_middle(self, start: int) -> int | None:
        """The middle of the longest run of truly quiet frames from frame `start` on, where a pause can be
        cut. None if there is none: the "pause" is a soft voice, and cutting would split its words."""
        quiet, best, run = self._quiet(), None, 0
        for i in range(start, len(self._levels)):
            run = run + 1 if self._levels[i] < quiet else 0
            if run >= QUIET_RUN and (best is None or run > best[1]):
                best = (i - run + 1, run)
        return None if best is None else best[0] + best[1] // 2

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

    No audio is skipped: a phrase's clip starts where the last one ended, trimmed only up to the first frame
    the segmenter's lenient `voiced()` check hears (a soft word below the speech threshold still counts),
    and a guess only stands if nothing voiced lies outside it.

    `show` sends the words so far as a Partial: committed text, then the guess or preview of the open
    phrase. Commits and guesses always run before previews and start as soon as they are due, so the full
    model is never behind by more than one preview pass (about 0.05 s). A preview needs `gap_s` of idle
    GPU before it, which leaves room for speech synthesis, and none starts once the open phrase has gone
    quiet: the guess is about to come.

    finish() is the release: it interrupts a commit or preview in flight (a guess is let finish if nothing was
    said after it: it may be the end), transcribes everything left in one quick pass and returns the whole
    text. A quick pass that hears nothing
    in voiced audio is done again at full accuracy, and if the text is still short for the speech (fewer
    than `min_words_per_s` words per second of it), one full pass over the whole recording decides.
    """

    def __init__(self, mic: AudioInput, stt: Transcriber, executor: Executor, sink: EventSink,
                 segmenter: PauseSegmenter, *, on_phrase: Callable[[str], object] | None = None,
                 show: bool = True, poll_s: float = 0.1, gap_s: float = 0.15, settle_s: float = 0.25,
                 min_new_s: float = 0.5, min_words_per_s: float | None = None,
                 monotonic: Callable[[], float] = time.monotonic):
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
        self._min_words_per_s = MIN_WORDS_PER_S if min_words_per_s is None else min_words_per_s
        self._monotonic = monotonic
        self._heard = 0  # samples fed to the segmenter
        self._covered = 0  # samples up to the end of the last committed phrase
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
        self._guessing: int | None = None  # the end of the guess in flight
        self._task: asyncio.Task | None = None

    @property
    def text(self) -> str:
        return join_phrases(self.phrases)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def finish(self, audio: Audio) -> str:
        """The rest of `audio` (the whole recording) transcribed after the phrases already committed.
        Returns all of it. Whatever is left, closed phrases and the open one, goes in one quick pass: the
        user is waiting now. None if a guess holds all of it."""
        await self._stop(audio)
        self._listen(audio[self._heard:])
        guess, self._guess, self._preview = self._guess, None, ""
        rest = audio[self._covered:]
        start = self._voice_start(rest)
        if start is None:
            self._show()
        elif guess is not None and self._guess_covers(guess, rest, len(audio)):
            log.debug("release: the guess covers the rest")
            self._commit(guess.text)
        else:
            self._commit(await self._sure(rest[start:]))
        self._pending.clear()
        self._covered = len(audio)
        await self._check_length(audio)
        return self.text

    def abort(self) -> None:
        """Drop everything, e.g. on cancel."""
        self._closing = True
        if self._task is not None:
            self._task.cancel()

    async def _stop(self, audio: Audio) -> None:
        """End the live passes. A guess in flight is let finish if nothing voiced came after it: it may be the
        end. Anything else in flight is interrupted."""
        self._closing = True
        task = self._task
        if task is None:
            return
        guessing = self._guessing
        if not self._passing:
            task.cancel()
        elif self._interruptible or (guessing is not None and self._has_voice(audio[guessing:])):
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
            await self._commit_next()
        elif seg.open_has_speech and seg.silence_s >= self._settle_s and self._guess is None:
            covered, end, open_start = self._covered, self._heard, seg.open_start
            audio = self._mic.peek(covered)[:end - covered]
            voice = self._voice_start(audio)
            start = covered + (voice if voice is not None else open_start - covered)
            self._guessing = end
            try:
                text = await self._pass(self._stt.transcribe, audio[start - covered:], self.text,
                                        quick=True, interruptible=False)
            finally:
                self._guessing = None
            if seg.open_start == open_start and seg.speech_end <= end:  # kept on release too: it may be the end
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

    async def _commit_next(self) -> None:
        """Commit the oldest closed phrase at full accuracy. It runs from the end of the last one, less silence."""
        cut = self._pending[0]
        audio = self._mic.peek(self._covered)[:cut.end - self._covered]
        voice = self._voice_start(audio)
        start = self._covered + voice if voice is not None else cut.start
        text = await self._pass(self._stt.transcribe, audio[start - self._covered:], self.text)
        self._pending.pop(0)
        self._covered = cut.end
        if self._guess is not None and self._guess.start < cut.end:
            self._guess = None
        self._preview = ""
        self._commit(text)

    def _guess_covers(self, guess: _Guess, audio: Audio, end: int) -> bool:
        """Does `guess` hold every voiced frame of `audio`, the recording from the last commit up to `end`?"""
        covered = self._covered
        return (covered <= guess.start <= guess.end <= end
                and not self._has_voice(audio[:guess.start - covered])
                and not self._has_voice(audio[guess.end - covered:]))

    def _voice_start(self, audio: Audio) -> int | None:
        """Where a clip of `audio` should start: a short lead before its first voiced frame. None: no voice."""
        voiced = self._segmenter.voiced(audio)
        if voiced.sum() < MIN_VOICED_FRAMES:
            return None
        lead = int(LEAD_S * STT_SAMPLE_RATE)
        return max(0, int(np.argmax(voiced)) * self._segmenter.frame - lead)

    def _has_voice(self, audio: Audio) -> bool:
        return int(self._segmenter.voiced(audio).sum()) >= MIN_VOICED_FRAMES

    async def _sure(self, audio: Audio) -> str:
        """A quick pass; if it heard nothing in audio with a voice, the full model again at full accuracy."""
        text = await self._pass(self._stt.transcribe, audio, self.text, quick=True)
        if not text and self._has_voice(audio):
            log.info("a quick pass heard nothing in %.1fs with a voice; again at full accuracy",
                     len(audio) / STT_SAMPLE_RATE)
            text = await self._pass(self._stt.transcribe, audio, self.text)
        return text

    async def _check_length(self, audio: Audio) -> None:
        """The safety net: text short for the speech heard means words went missing somewhere. One full pass
        over the whole recording, as with stream = "off", and its text wins if it has more words. Typed
        phrases are in the app already, so type mode only logs it."""
        speech_s = self._segmenter.speech_s
        words = len(self.text.split())
        if speech_s < 1.0 or words >= self._min_words_per_s * speech_s:
            return
        if self._on_phrase is not None:
            log.warning("typed %d words for %.1fs of speech; some may be missing", words, speech_s)
            return
        whole = await self._pass(self._stt.transcribe, audio, "")
        log.warning("%d words for %.1fs of speech looked short; the whole recording gave %d", words, speech_s,
                    len(whole.split()))
        if len(whole.split()) > words:
            self.phrases = [whole]
            self._show()

    def _commit(self, text: str) -> None:
        text = text.strip()
        if text:
            self.phrases.append(text)
            if self._on_phrase is not None:
                self._on_phrase(text)
        self._show()

    async def _pass(self, fn: Callable[..., str], audio: Audio, before: str | None, *, quick: bool = False,
                    interruptible: bool = True) -> str:
        """Run `fn` on the STT executor. `before` None: a preview (no context, always quick). A live pass
        still waiting for the STT thread (behind Transcriber.wake) when the release comes is skipped."""
        started = self._monotonic()
        self._passing = True
        self._interruptible = interruptible
        closing = self._closing

        def run() -> str:
            if interruptible and self._closing and not closing:
                raise Interrupted()
            return fn(audio) if before is None else fn(audio, before, quick=quick)

        try:
            text = await asyncio.get_running_loop().run_in_executor(self._executor, run)
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
