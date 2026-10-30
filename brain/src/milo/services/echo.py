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
NOISE_WINDOW_BLOCKS = 125  # 2 s


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
    above the echo the canceller usually leaves behind, for `HOLD_BLOCKS` blocks in a row with at most one
    quieter block between. The echo it leaves follows the loudest recent echo, decaying like a room's
    reverberation, so the tail of Milo's last word doesn't count as the user. Until the canceller has heard
    enough of Milo and takes a fair part of his echo out (`learning`), the bar is the reference's level plus
    the speaker-to-mic coupling measured so far, which only clear speech passes. A room the canceller can't
    learn (a distorting speaker) keeps that bar: the user then has to be louder than Milo in the mic.
    """

    SPEECH_OVER_NOISE_DB = 12.0
    SPEECH_OVER_ECHO_DB = 8.0
    LEARNING_MARGIN_DB = 6.0
    HOLD_BLOCKS = 9  # 144 ms
    LEARN_BLOCKS = 30  # about half a second of Milo's voice
    LEARNED_DB = 6.0  # and the canceller takes at least this much of his echo out
    DECAY_DB = 1.0  # per block: about 60 dB a second, a small room's reverberation
    PLAYING_DB = -60.0

    def __init__(self, canceller: EchoCanceller | None = None):
        self.canceller = canceller or EchoCanceller()
        self._noise_db: float | None = None  # the quiet room: the quietest residual of the last two seconds
        self._quiet: deque[float] = deque(maxlen=NOISE_WINDOW_BLOCKS)
        self._leak_db = 0.0  # residual minus recent echo, in blocks where only Milo spoke
        self._coupling_db = 0.0  # mic minus reference: how loud Milo is in the mic, until the canceller knows
        self._removed_db = 0.0  # mic minus residual while Milo plays: how much echo the canceller takes out
        self._echo_env = -120.0
        self._ref_env = -120.0
        self._echo_blocks = 0
        self._run = 0
        self._miss = 0
        self.talking = False
        self.speech_now = False
        """The last block was over the bar: a speech sound, whether or not it lasted."""
        self.residual = np.zeros(0)
        """The last block with Milo's echo taken out."""

    @property
    def learning(self) -> bool:
        return self._echo_blocks < self.LEARN_BLOCKS or self._removed_db < self.LEARNED_DB

    def process(self, mic: np.ndarray, ref: np.ndarray) -> bool:
        """Feed one block of mic and the reference played with it. True once the user is talking."""
        residual, echo = self.canceller.process(mic, ref, adapt=not self._run)
        res_db = _db(float(np.mean(residual ** 2)))
        mic_db = _db(float(np.mean(np.square(mic))))
        self._echo_env = max(_db(float(np.mean(echo ** 2))), self._echo_env - self.DECAY_DB)
        self._ref_env = max(_db(float(np.mean(np.square(ref)))), self._ref_env - self.DECAY_DB)
        playing = self._ref_env > self.PLAYING_DB
        if self._noise_db is None:
            self._noise_db = res_db
        bar = self._noise_db + self.SPEECH_OVER_NOISE_DB
        if playing:
            bar = max(bar, self._echo_env + self._leak_db + self.SPEECH_OVER_ECHO_DB)
            if self.learning:
                bar = max(bar, self._ref_env + self._coupling_db + self.LEARNING_MARGIN_DB)
        self.residual = residual
        self.speech_now = res_db > bar
        if self.speech_now:
            self._run += 1
            self._miss = 0
        elif self._run:
            self._miss += 1
            if self._miss > 1:
                self._run = self._miss = 0
        if not self._run:
            self._learn(res_db, mic_db, playing)
        self.talking = self._run >= self.HOLD_BLOCKS
        return self.talking

    def _learn(self, res_db: float, mic_db: float, playing: bool) -> None:
        # The floor is the quietest block of the last two seconds: it follows a louder room (a fan coming on)
        # within two seconds, and the tail of Milo's last word, never the quietest part, can't lift it.
        self._quiet.append(res_db)
        self._noise_db = min(self._quiet)
        if not playing:
            return
        if self._ref_env > self.PLAYING_DB + 20 and mic_db > self._noise_db + 6:
            self._echo_blocks += 1
            fast = self.learning
            self._coupling_db += (0.3 if fast else 0.02) * (mic_db - self._ref_env - self._coupling_db)
            self._leak_db += (0.2 if fast else 0.03) * (min(res_db - self._echo_env, 6.0) - self._leak_db)
            self._removed_db += 0.1 * (mic_db - res_db - self._removed_db)
