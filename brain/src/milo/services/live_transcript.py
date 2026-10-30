"""Transcription while the user is still speaking ([dictation] stream = "preview" or "type").

A Whisper pass costs about the same whatever the length up to 30 s, because the encoder always sees a
padded 30 s window: 1.2 s for large-v3-turbo on an M3, 0.1 to 0.25 s for the preview model. So passes run
one at a time, back to back with a short gap, and each covers only the phrase after the last pause, never
the whole growing recording.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from concurrent.futures import Executor

import numpy as np

from milo.core.events import Dictation, Partial
from milo.core.ports import AudioInput, DictationHistory, EventSink, TextCleaner
from milo.core.types import STT_SAMPLE_RATE, Audio

log = logging.getLogger("milo.live_transcript")


class PauseSegmenter:
    """Cuts a growing recording into phrases at pauses, by loudness alone.

    feed() takes the next samples and returns the phrases a pause closed, as (start, end) sample indexes
    into the whole recording. The cut lies in the middle of the pause, so both sides keep some silence.
    A phrase needs `min_speech_s` of speech; clicks and breaths alone never make one, and silence before
    speech is trimmed to `lead_s`. A phrase longer than `max_s` without a pause is cut at its quietest
    frame, which keeps every pass inside one Whisper window.
    """

    def __init__(self, sample_rate: int = STT_SAMPLE_RATE, *, pause_s: float = 0.7, max_s: float = 20.0,
                 min_speech_s: float = 0.2, lead_s: float = 0.3, min_rms: float = 0.008, max_rms: float = 0.03,
                 noise_ratio: float = 3.0, frame_s: float = 0.03):
        self._frame = int(sample_rate * frame_s)
        self._pause = max(2, round(pause_s / frame_s))
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

    @property
    def open_start(self) -> int:
        """Sample index where the phrase not yet closed by a pause starts."""
        return self._open * self._frame

    @property
    def open_has_speech(self) -> bool:
        return self._speech >= self._min_speech

    def feed(self, samples: Audio) -> list[tuple[int, int]]:
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

    def _step(self, level: float) -> tuple[int, int] | None:
        if level > 1e-5:  # some mics deliver exact zeros while starting up
            self._noise = level if self._noise is None else min(self._noise, level)
        self._levels.append(level)
        if level >= self._threshold():
            self._speech += 1
            self._silence = 0
        else:
            self._silence += 1
        if self._silence >= self._pause:
            if self.open_has_speech:
                return self._cut(len(self._levels) - self._silence + self._pause // 2)
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

    def _cut(self, at: int) -> tuple[int, int]:
        """Close the open phrase `at` frames in; the frames after it open the next one."""
        start = self.open_start
        self._open += at
        self._levels = self._levels[at:]
        threshold = self._threshold()
        self._speech = sum(level >= threshold for level in self._levels)
        self._silence = 0
        for level in reversed(self._levels):
            if level >= threshold:
                break
            self._silence += 1
        return start, self.open_start


class TypedDictation:
    """One recording pasted phrase by phrase. Each phrase is cleaned on its own; all but the first get a
    leading space, since they continue what was just pasted."""

    def __init__(self, cleaner: TextCleaner, history: DictationHistory | None, sink: EventSink):
        self._cleaner = cleaner
        self._history = history
        self._sink = sink
        self.texts: list[str] = []

    def add(self, transcript: str) -> str:
        """Clean and paste one phrase. Returns the cleaned text, "" if nothing was left to paste."""
        text = self._cleaner.clean(transcript)
        if not text:
            return ""
        self._sink.emit(Dictation(f" {text}" if self.texts else text))
        self.texts.append(text)
        return text

    def finish(self, app: str | None) -> None:
        """Log what was pasted as one history entry."""
        if self._history is None or not self.texts:
            return
        try:
            self._history.append(" ".join(self.texts), app)
        except Exception:
            log.exception("could not save dictation history")


class LiveTranscript:
    """Transcribes a recording while it runs, on the STT executor, one pass at a time.

    Every `poll_s` it reads the new audio and lets the segmenter close phrases at pauses. A closed phrase
    is transcribed once: with `typed`, by `transcribe` and pasted at once; otherwise by the faster
    `preview` and kept for the preview. Then the open phrase after the last pause is transcribed again with
    `preview` and shown as a Partial. Only typed text needs the full model, so a final pass rarely waits
    long behind a live one. `gap_s` of idle GPU between passes leaves room for speech synthesis.
    """

    def __init__(self, mic: AudioInput, transcribe: Callable[[Audio], str], executor: Executor, sink: EventSink,
                 segmenter: PauseSegmenter, typed: TypedDictation | None = None, *,
                 preview: Callable[[Audio], str] | None = None, poll_s: float = 0.2, gap_s: float = 0.3,
                 min_new_s: float = 0.5, monotonic: Callable[[], float] = time.monotonic):
        self._mic = mic
        self._transcribe = transcribe
        self._preview = preview or transcribe
        self._executor = executor
        self._sink = sink
        self._segmenter = segmenter
        self.typed = typed
        self._poll_s = poll_s
        self._gap_s = gap_s
        self._min_new = int(min_new_s * STT_SAMPLE_RATE)
        self._monotonic = monotonic
        self._pending: list[tuple[int, int]] = []  # closed phrases not yet transcribed
        self._phrases: list[str] = []  # preview text of closed phrases
        self._shown = ""
        self._committing = False
        self._closing = False
        self._task: asyncio.Task | None = None

    @property
    def tail_start(self) -> int:
        """Where the audio no phrase has been typed for starts. Read it after close()."""
        return self._pending[0][0] if self._pending else self._segmenter.open_start

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Stop live passes. A phrase being transcribed for typing finishes first, so phrases land in order;
        a preview pass is dropped (it still finishes on the STT thread, MLX can't be interrupted)."""
        self._closing = True
        task = self._task
        if task is None:
            return
        if not (self._committing and self.typed is not None):
            task.cancel()
        await asyncio.wait({task})

    def abort(self) -> None:
        """Drop everything, e.g. on cancel."""
        self._closing = True
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        heard = previewed = 0
        idle_s = self._poll_s
        try:
            while not self._closing:
                await asyncio.sleep(idle_s)
                idle_s = self._poll_s
                new = self._mic.peek(heard)
                heard += len(new)
                self._pending.extend(self._segmenter.feed(new))
                while self._pending:
                    start, end = self._pending[0]
                    self._committing = True
                    try:
                        text = await self._pass(self._mic.peek(start)[:end - start],
                                                self._transcribe if self.typed is not None else self._preview)
                    finally:
                        self._committing = False
                    self._pending.pop(0)
                    if self.typed is not None:
                        self.typed.add(text)
                    elif text:
                        self._phrases.append(text)
                    self._show("")
                    idle_s = max(self._poll_s, self._gap_s)
                    if self._closing:
                        return
                if self._segmenter.open_has_speech and heard - previewed >= self._min_new:
                    previewed = heard
                    self._show(await self._pass(self._mic.peek(self._segmenter.open_start), self._preview))
                    idle_s = max(self._poll_s, self._gap_s)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("live transcription failed; the final pass still runs")

    async def _pass(self, audio: Audio, transcribe: Callable[[Audio], str]) -> str:
        started = self._monotonic()
        text = await asyncio.get_running_loop().run_in_executor(self._executor, transcribe, audio)
        log.debug("live pass %.1fs audio in %.2fs", len(audio) / STT_SAMPLE_RATE, self._monotonic() - started)
        return text.strip()

    def _show(self, open_text: str) -> None:
        parts = [open_text] if self.typed is not None else [*self._phrases, open_text]
        text = " ".join(p for p in parts if p)
        if text != self._shown:
            self._shown = text
            self._sink.emit(Partial(text))
