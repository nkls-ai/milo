"""Talking over Milo: while he speaks, a microphone listens for the user, and he goes quiet when they start.

`[chat] voice_barge_in = true` turns it on. It needs an output that says what it played (PlaybackTap) and a
microphone that says when it heard (`started_at`), both on the same clock, so each block of the mic can be
matched with the audio that was playing at that moment and Milo's own voice taken out (`echo.py`).

When the user talks over him, LiveTalk.hold() silences Milo at once and keeps his place. The watcher goes on
recording, from a little before the user started, until they pause. Real words start a new turn. Nothing (a
cough, a door, a false alarm) and Milo goes on where he was, so a mistake costs a second, not the answer.
The talk key always wins: once Listening has the mic, the watcher lets go.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Executor

import numpy as np

from milo.core.logtext import private
from milo.core.ports import AudioInput, PlaybackTap, Transcriber
from milo.core.types import STT_SAMPLE_RATE, MiloState

from .echo import BLOCK, EchoCanceller, TalkDetector
from .live_talk import LiveTalk
from .speaker import Speaker
from .ui_state import UiState

log = logging.getLogger("milo.barge_in")

POLL_S = 0.03
PRE_ROLL_S = 0.35  # kept from before the detector was sure: the start of the user's first word
END_SILENCE_S = 0.8  # a pause this long ends what the user says
NO_SPEECH_S = 1.2  # nothing more after the trigger: a false alarm, Milo goes on
MIN_SPEECH_S = 0.2  # less speech than this in total, trigger included, isn't worth transcribing
MAX_CAPTURE_S = 30.0


def reference_for(rate: int, blocks: list[tuple[float, np.ndarray]], start: float, n: int) -> np.ndarray:
    """What was playing during the `n` mic samples from time `start`, resampled to the mic's rate. Zeros where
    nothing played."""
    times = start + np.arange(n) / STT_SAMPLE_RATE
    out = np.zeros(n)
    for at, block in blocks:
        pos = (times - at) * rate
        inside = (pos >= 0) & (pos <= len(block) - 1)
        if inside.any():
            out[inside] = np.interp(pos[inside], np.arange(len(block)), block)
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower())


def own_words(heard: str, said: str) -> bool:
    """The transcript is mostly Milo's own recent words: his echo got through, not the user."""
    words = _words(heard)
    mine = set(_words(said))
    return bool(words) and sum(w in mine for w in words) >= 0.6 * len(words)


class BargeIn:
    """Watches the mic while Milo speaks and hands what the user says to LiveTalk (see the module docstring)."""

    def __init__(self, mic: AudioInput, tap: PlaybackTap, transcriber: Transcriber, executor: Executor,
                 ui: UiState, live_talk: LiveTalk, speaker: Speaker, *, mic_busy: Callable[[], bool],
                 poll_s: float = POLL_S):
        self._mic = mic
        self._tap = tap
        self._transcriber = transcriber
        self._executor = executor
        self._ui = ui
        self._live_talk = live_talk
        self._speaker = speaker
        self._mic_busy = mic_busy
        self._poll_s = poll_s
        self._canceller = EchoCanceller()  # kept between replies: the room and the speakers don't change
        self.barge_ins = 0
        self.false_alarms = 0

    def _should_watch(self) -> bool:
        return self._speaker.active and not self._speaker.held and not self._mic_busy()

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._poll_s)
            if self._should_watch():
                try:
                    await self._watch()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("listening for barge-in failed; trying again with the next reply")
                    await asyncio.sleep(5)

    async def _watch(self) -> None:
        try:
            self._mic.start(lambda level: None)
        except Exception as e:
            log.warning("no mic for barge-in: %s", e)
            await asyncio.sleep(5)
            return
        try:
            detector = TalkDetector(self._canceller)
            index = 0
            recent: deque[np.ndarray] = deque(maxlen=int(PRE_ROLL_S * STT_SAMPLE_RATE / BLOCK) + 1)
            while self._should_watch():
                await asyncio.sleep(self._poll_s)
                index, blocks = self._blocks(index, detector, recent)
                if any(talking for talking, _ in blocks):
                    await self._capture(detector, index, list(recent))
                    return
        finally:
            if self._mic.active:
                self._mic.stop()

    def _blocks(self, index: int, detector: TalkDetector, kept: deque | list) -> tuple[int, list]:
        """Run the new mic blocks through the detector. Returns the next index and (talking, speech) per block;
        each block's residual, the mic without Milo's echo, lands in `kept`."""
        started = getattr(self._mic, "started_at", None)
        if started is None:
            return index, []
        audio = self._mic.peek(index)
        n = len(audio) // BLOCK * BLOCK
        if not n:
            return index, []
        t0 = started + index / STT_SAMPLE_RATE
        rate, played = self._tap.played(t0 - 0.2)
        ref = reference_for(rate, played, t0, n)
        out = []
        for i in range(0, n, BLOCK):
            talking = detector.process(audio[i:i + BLOCK], ref[i:i + BLOCK])
            kept.append(detector.residual.astype(np.float32))
            out.append((talking, detector.speech_now))
        return index + n, out

    async def _capture(self, detector: TalkDetector, index: int, pre_roll: list[np.ndarray]) -> None:
        if not self._live_talk.hold():
            return
        self.barge_ins += 1
        log.info("barge-in: the user talked over Milo")
        self._ui.set_state(MiloState.LISTENING)
        loop = asyncio.get_running_loop()
        began = last_speech = loop.time()
        speech_blocks = detector.HOLD_BLOCKS
        heard = list(pre_roll)
        while True:
            await asyncio.sleep(self._poll_s)
            if self._mic_busy():
                log.info("the talk key took over from barge-in")
                return  # Listening has the turn now, and its own recording
            index, blocks = self._blocks(index, detector, heard)
            speech = sum(1 for _, sound in blocks if sound)
            if speech:
                speech_blocks += speech
                last_speech = loop.time()
            now = loop.time()
            if last_speech == began and now - began > NO_SPEECH_S:
                break
            if last_speech > began and now - last_speech > END_SILENCE_S:
                break
            if now - began > MAX_CAPTURE_S:
                break
        if speech_blocks * BLOCK / STT_SAMPLE_RATE < MIN_SPEECH_S or last_speech == began:
            self._false_alarm()
            return
        self._ui.set_state(MiloState.TRANSCRIBING)
        audio = np.concatenate(heard)
        started = time.monotonic()
        try:
            text = (await loop.run_in_executor(self._executor, self._transcriber.transcribe, audio)).strip()
        except Exception:
            log.exception("transcribing a barge-in failed")
            text = ""
        log.info("barge-in stt %.2fs audio in %.2fs: %s", len(audio) / STT_SAMPLE_RATE, time.monotonic() - started,
                 private(text))
        if text and not own_words(text, self._speaker.recent_text):
            self._live_talk.start(text)
        else:
            self._false_alarm()

    def _false_alarm(self) -> None:
        self.false_alarms += 1
        log.info("barge-in heard no words; going on")
        if not self._live_talk.resume():
            self._ui.rest()
