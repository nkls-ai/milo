"""Hearing the user over Milo's own voice: an echo canceller and a speech detector for barge-in.

While Milo speaks through the Mac's speakers, the microphone hears him too, often as loud as a user sitting
at the laptop. A plain loudness check would stop him at his own first word. So the mic signal first loses
the echo of what is being played: `EchoCanceller` learns the path from the speaker to the microphone
(a partitioned-block frequency-domain NLMS filter, 128 ms long) and subtracts its estimate. `TalkDetector`
then asks whether what is left is speech: louder than the room's noise floor, louder than the echo the
canceller typically leaves behind, and for long enough that a cough or a click doesn't count.

Both work on 16 kHz blocks of `BLOCK` samples. The reference must be what was played at the same moment as
the mic block was heard; `services/barge_in.py` lines the two up by their timestamps.
"""

from __future__ import annotations

from collections import deque

import numpy as np

RATE = 16_000
BLOCK = 256  # 16 ms
TAPS = 2048  # 128 ms of echo path: room reflections plus a few ms of timestamp error


def _db(power: float) -> float:
    return 10.0 * np.log10(power + 1e-12)


class EchoCanceller:
    """Subtracts the echo of `ref` from `mic`, block by block. Adapts only while told the user is quiet."""

    def __init__(self, block: int = BLOCK, taps: int = TAPS, step: float = 0.5):
        self.block = block
        self.parts = taps // block
        self.step = step
        bins = block + 1
        self._weights = np.zeros((self.parts, bins), dtype=np.complex128)
        self._spectra: deque[np.ndarray] = deque([np.zeros(bins, np.complex128)] * self.parts, maxlen=self.parts)
        self._last_ref = np.zeros(block)
        self._power = np.full(bins, 1e-6)

    def process(self, mic: np.ndarray, ref: np.ndarray, *, adapt: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """(residual, echo estimate) for one block."""
        b = self.block
        x = np.fft.rfft(np.concatenate([self._last_ref, ref]))
        self._last_ref = np.asarray(ref, dtype=np.float64).copy()
        self._spectra.appendleft(x)
        echo_spectrum = np.zeros_like(x)
        for w, xs in zip(self._weights, self._spectra):
            echo_spectrum += w * xs
        echo = np.fft.irfft(echo_spectrum)[b:]
        residual = np.asarray(mic, dtype=np.float64) - echo
        self._power = 0.8 * self._power + 0.2 * (np.abs(x) ** 2)
        if adapt:
            err = np.fft.rfft(np.concatenate([np.zeros(b), residual]))
            norm = self.step / (self._power * self.parts + 1e-3 * b)
            for p, xs in enumerate(self._spectra):
                grad = np.fft.irfft(np.conj(xs) * err * norm)
                grad[b:] = 0  # keep the filter causal and the convolution linear
                self._weights[p] += np.fft.rfft(grad)
        return residual, echo


class TalkDetector:
    """Decides, block by block, whether the user talks over Milo.

    The user talks when the residual is `SPEECH_OVER_NOISE_DB` above the noise floor and `SPEECH_OVER_ECHO_DB`
    above the echo the canceller usually leaves at this playback level, for `HOLD_BLOCKS` blocks in a row with
    at most one quiet block between. Until the canceller has heard enough echo to know how much it leaves
    (`learning`), the bar is the raw echo estimate instead, which only very clear speech passes.
    """

    SPEECH_OVER_NOISE_DB = 12.0
    SPEECH_OVER_ECHO_DB = 8.0
    HOLD_BLOCKS = 8  # 128 ms
    LEARN_BLOCKS = 30  # about half a second of Milo's voice

    def __init__(self, canceller: EchoCanceller | None = None):
        self.canceller = canceller or EchoCanceller()
        self._noise_db = None  # the quiet room, from blocks without playback or speech
        self._leak_db = 0.0  # residual minus echo estimate, in dB, in blocks where only Milo spoke
        self._echo_blocks = 0
        self._run = 0
        self._miss = 0
        self.talking = False

    @property
    def learning(self) -> bool:
        return self._echo_blocks < self.LEARN_BLOCKS

    def process(self, mic: np.ndarray, ref: np.ndarray) -> bool:
        """Feed one block of mic and the reference played with it. True once the user is talking."""
        residual, echo = self.canceller.process(mic, ref, adapt=not self._run)
        res_db = _db(float(np.mean(residual ** 2)))
        echo_db = _db(float(np.mean(echo ** 2)))
        ref_db = _db(float(np.mean(np.square(ref))))
        playing = ref_db > -60
        if self._noise_db is None:
            self._noise_db = res_db
        bar = self._noise_db + self.SPEECH_OVER_NOISE_DB
        if playing:
            leak = self._leak_db if not self.learning else max(self._leak_db, 6.0)
            bar = max(bar, echo_db + leak + self.SPEECH_OVER_ECHO_DB)
        speech = res_db > bar
        if speech:
            self._run += 1
            self._miss = 0
        elif self._run:
            self._miss += 1
            if self._miss > 1:
                self._run = self._miss = 0
        if not self._run:
            self._learn(res_db, echo_db, playing)
        self.talking = self._run >= self.HOLD_BLOCKS
        return self.talking

    def _learn(self, res_db: float, echo_db: float, playing: bool) -> None:
        if not playing:
            # The floor follows a quieter room at once and a louder one slowly (a fan coming on).
            self._noise_db = res_db if res_db < self._noise_db else self._noise_db + 0.02 * (res_db - self._noise_db)
            return
        if echo_db > self._noise_db + 6:
            self._echo_blocks += 1
            alpha = 0.2 if self.learning else 0.03
            self._leak_db += alpha * (min(res_db - echo_db, 6.0) - self._leak_db)
