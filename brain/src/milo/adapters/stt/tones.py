"""`[stt] use = "tones"`: a stand-in for Whisper in end-to-end tests. It hears words spoken as tones.

Each word of a vocabulary is a sine at its own frequency (`ToneCodec`). A test turns a script into such
"speech", with pauses, soft words and room noise like a real recording, and plays it into a brain through
the WAV microphone; this transcriber hears every tone in the audio it gets, however soft, the way Whisper
hears a soft voice. A pass takes a set time, so release timings stay realistic, and stops on interrupt().
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from milo.core.registry import TRANSCRIBERS, AdapterContext, options_from
from milo.core.types import STT_SAMPLE_RATE, Audio, Interrupted

BASE_HZ = 300.0
STEP_HZ = 9.0
FRAME = 320  # 20 ms
MIN_FRAMES = 4  # a word lasts at least 80 ms; less is the edge of a word cut off by the clip
TONAL = 8.0  # a frame holds a tone if its spectral peak stands this far above the median


class ToneCodec:
    """Words to tones and back. Word i is a sine at BASE_HZ + i * STEP_HZ, lasting about as long as it takes
    to say it, and rising and falling once per syllable like a voice, so its quiet moments are as quiet as
    a voice's; words are separated by a short silence."""

    def __init__(self, words: list[str]):
        self.words = list(dict.fromkeys(w.lower() for w in words))
        self._index = {w: i for i, w in enumerate(self.words)}
        if BASE_HZ + STEP_HZ * len(self.words) > STT_SAMPLE_RATE * 0.45:
            raise ValueError(f"too many words for tones: {len(self.words)}")

    def frequency(self, word: str) -> float:
        return BASE_HZ + STEP_HZ * self._index[word.lower()]

    def speak(self, text: str, level: float = 0.1, gap_s: float = 0.06) -> Audio:
        """`text` as tones of RMS `level`, each word followed by `gap_s` of silence."""
        parts = []
        for word in text.split():
            seconds = 0.12 + 0.03 * len(word)
            t = np.arange(int(seconds * STT_SAMPLE_RATE)) / STT_SAMPLE_RATE
            ramp = np.minimum(1.0, np.minimum(t, t[-1] - t) / 0.01)  # no clicks at the edges
            syllables = max(1, round(len(word) / 3))
            envelope = 0.3 + 0.7 * np.abs(np.sin(np.pi * syllables * t / t[-1]))
            wave = level * np.sqrt(2) * ramp * envelope * np.sin(2 * np.pi * self.frequency(word) * t)
            parts.append(wave.astype(np.float32))
            parts.append(np.zeros(int(gap_s * STT_SAMPLE_RATE), dtype=np.float32))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def hear(self, audio: Audio) -> list[str]:
        """The words whose tones are in `audio`, in order."""
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        n = len(audio) // FRAME
        if n == 0:
            return []
        frames = audio[:n * FRAME].reshape(n, FRAME) * np.hanning(FRAME)
        spectra = np.abs(np.fft.rfft(frames, axis=1))
        peaks = spectra.argmax(axis=1)
        tonal = spectra.max(axis=1) > TONAL * (np.median(spectra, axis=1) + 1e-9)
        words, start = [], None
        for i in range(n + 1):
            same = i < n and tonal[i] and start is not None and abs(int(peaks[i]) - int(peaks[i - 1])) <= 1
            if start is not None and not same:
                if i - start >= MIN_FRAMES:
                    words.append(self._word(audio[start * FRAME:i * FRAME]))
                start = None
            if start is None and i < n and tonal[i]:
                start = i
        return [w for w in words if w is not None]

    def _word(self, run: Audio) -> str | None:
        size = 1 << 16  # zero-padded: a fine enough grid to tell words 9 Hz apart
        spectrum = np.abs(np.fft.rfft(run * np.hanning(len(run)), size))
        hz = spectrum.argmax() * STT_SAMPLE_RATE / size
        i = round((hz - BASE_HZ) / STEP_HZ)
        return self.words[i] if 0 <= i < len(self.words) and abs(hz - self.frequency(self.words[i])) < STEP_HZ / 2 \
            else None


class ToneTranscriber:
    """A Transcriber that hears tones. A full pass takes `full_s`, a quick one `quick_s` plus `quick_per_s`
    for each second of audio, a preview `preview_s`."""

    def __init__(self, codec: ToneCodec, *, full_s: float = 0.5, quick_s: float = 0.1, quick_per_s: float = 0.01,
                 preview_s: float = 0.02, wake_s: float = 0.02):
        self.codec = codec
        self._full_s = full_s
        self._quick_s = quick_s
        self._quick_per_s = quick_per_s
        self._preview_s = preview_s
        self._wake_s = wake_s
        self._stop = threading.Event()

    def warm(self) -> None:
        pass

    def wake(self) -> None:
        self._stop.clear()
        time.sleep(self._wake_s)

    def transcribe(self, audio: Audio, before: str = "", *, quick: bool = False) -> str:
        self._stop.clear()
        seconds = len(audio) / STT_SAMPLE_RATE
        self._work(self._quick_s + self._quick_per_s * seconds if quick else self._full_s * max(1.0, seconds / 30))
        return self._text(audio)

    def preview(self, audio: Audio) -> str:
        self._stop.clear()
        self._work(self._preview_s)
        return self._text(audio)

    def interrupt(self) -> None:
        self._stop.set()

    def _work(self, seconds: float) -> None:
        if self._stop.wait(seconds):
            raise Interrupted()

    def _text(self, audio: Audio) -> str:
        return " ".join(self.codec.hear(audio))


@dataclass(frozen=True)
class TonesOptions:
    words: str = ""  # a JSON list of the vocabulary, in the order that gives each word its tone
    full_s: float = 0.5  # about Whisper's times on an M3, so a release waits as long as it would
    quick_s: float = 0.1
    quick_per_s: float = 0.01
    preview_s: float = 0.02
    wake_s: float = 0.02


@TRANSCRIBERS.register("tones")
def _tones(options: Mapping[str, Any], ctx: AdapterContext) -> ToneTranscriber:
    o = options_from(TonesOptions, options, "stt.tones")
    words = json.loads(Path(o.words).expanduser().read_text()) if o.words else []
    return ToneTranscriber(ToneCodec(words), full_s=o.full_s, quick_s=o.quick_s, quick_per_s=o.quick_per_s,
                           preview_s=o.preview_s, wake_s=o.wake_s)
