"""Shaping synthesized pieces into one continuous voice: edges, pauses between pieces and loudness.

A TTS engine returns each piece as a standalone clip: OmniVoice pads both ends with about 200 ms of silence and
fades in and out over 100 ms, and its loudness drifts by several dB from piece to piece. Played back to back,
that is 400 ms or more of silence at every join, even mid-sentence, and a voice that jumps in volume. So each
piece is trimmed to its speech, levelled, and followed by a pause that fits how its text ended: a full stop
gets a sentence pause, a comma a short breath, a piece cut mid-clause almost none.
"""

from __future__ import annotations

import numpy as np

from milo.core.types import Audio

SILENCE_DB = -45.0  # a 10 ms frame quieter than this (dBFS) is silence
KEEP_LEAD_S = 0.03  # silence kept before the first sound, so a soft onset isn't clipped
KEEP_TAIL_S = 0.06  # and after the last, for a decaying consonant
EDGE_FADE_S = 0.008  # a short fade at a new edge, so trimming never clicks

SENTENCE_PAUSE_S = 0.30
CLAUSE_PAUSE_S = 0.16
RUN_ON_PAUSE_S = 0.04  # a piece cut where the text had no punctuation: keep talking
END_PAD_S = 0.25
"""Silence after the last piece. Output devices, Bluetooth ones most, need it to play out the final syllable
before the stream closes."""

TARGET_DB = -20.0  # speech loudness (dBFS RMS over the frames with sound)
MAX_GAIN_DB = 8.0
PEAK = 0.89  # about -1 dBFS


def pause_after(text: str) -> float:
    """How long to pause after a piece, from its last character."""
    end = text.rstrip().rstrip("\"'”’)]")[-1:]
    if end in (".", "!", "?", "…"):
        return SENTENCE_PAUSE_S
    if end in (",", ";", ":", "–", "—"):
        return CLAUSE_PAUSE_S
    return RUN_ON_PAUSE_S


def _frame_db(audio: np.ndarray, frame: int) -> np.ndarray:
    n = len(audio) // frame
    if n == 0:
        return np.zeros(0)
    frames = audio[:n * frame].reshape(n, frame)
    return 20 * np.log10(np.sqrt(np.mean(np.square(frames), axis=1)) + 1e-9)


def trim(audio: Audio, sample_rate: int) -> Audio:
    """Cut the silence around the speech, keeping a little on each side. Audio with no sound comes back empty."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    frame = max(1, sample_rate // 100)
    loud = np.flatnonzero(_frame_db(audio, frame) > SILENCE_DB)
    if not len(loud):
        return audio[:0]
    start = max(0, loud[0] * frame - int(KEEP_LEAD_S * sample_rate))
    end = min(len(audio), (loud[-1] + 1) * frame + int(KEEP_TAIL_S * sample_rate))
    out = audio[start:end].copy()
    fade = min(len(out) // 2, int(EDGE_FADE_S * sample_rate))
    if fade > 0:
        ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))).astype(np.float32)
        if start > 0:
            out[:fade] *= ramp
        if end < len(audio):
            out[-fade:] *= ramp[::-1]
    return out


def level(audio: Audio, sample_rate: int) -> Audio:
    """Bring speech to TARGET_DB, boosting at most MAX_GAIN_DB so a soft "hm" stays soft, and keep peaks under
    PEAK. Every piece of a reply then sits at the same loudness."""
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    db = _frame_db(audio, max(1, sample_rate // 100))
    loud = db[db > SILENCE_DB]
    if not len(loud):
        return audio
    speech_db = 10 * np.log10(np.mean(10 ** (loud / 10)))
    gain = 10 ** (min(MAX_GAIN_DB, TARGET_DB - speech_db) / 20)
    peak = float(np.max(np.abs(audio))) * gain
    if peak > PEAK:
        gain *= PEAK / peak
    return (audio * gain).astype(np.float32)


def shape(audio: Audio, sample_rate: int) -> Audio:
    """One piece ready to queue: trimmed to its speech and levelled. The pause after it is the caller's."""
    return level(trim(audio, sample_rate), sample_rate)


def silence(seconds: float, sample_rate: int) -> Audio:
    return np.zeros(max(0, int(round(seconds * sample_rate))), dtype=np.float32)
