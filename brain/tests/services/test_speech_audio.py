import asyncio
import time

import numpy as np

from milo.core.types import Emotion
from milo.services.speech_audio import (CLAUSE_PAUSE_S, KEEP_LEAD_S, KEEP_TAIL_S, MAX_GAIN_DB, PEAK,
                                        RUN_ON_PAUSE_S, SENTENCE_PAUSE_S, TARGET_DB, level, pause_after, shape, trim)
from tests.fakes import FakeVoice
from tests.services.stack import Stack

SR = 24_000


def tone(seconds: float, amplitude: float = 0.1, freq: float = 220.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def quiet(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def rms_db(audio: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(np.square(audio))))


def test_trim_cuts_the_engine_padding_down_to_a_little_breath():
    clip = np.concatenate([quiet(0.2), tone(1.0), quiet(0.22)])  # what OmniVoice returns around a piece
    out = trim(clip, SR)
    assert abs(len(out) / SR - (1.0 + KEEP_LEAD_S + KEEP_TAIL_S)) < 0.02
    assert abs(out[0]) < 1e-4 and abs(out[-1]) < 1e-4, "starts and ends in silence, so no click"


def test_trim_fades_an_edge_it_cuts_through_but_leaves_untouched_ends_alone():
    clip = np.concatenate([tone(0.5, 0.3), quiet(0.3)])
    out = trim(clip, SR)
    assert out[0] == clip[0], "nothing was cut at the start"
    assert abs(out[-1]) < 1e-3


def test_trim_of_silence_is_empty():
    assert len(trim(quiet(0.5), SR)) == 0


def test_level_brings_pieces_to_one_loudness():
    soft, loud = level(tone(1.0, 0.08), SR), level(tone(1.0, 0.3), SR)
    assert abs(rms_db(soft) - TARGET_DB) < 0.5 and abs(rms_db(loud) - TARGET_DB) < 0.5


def test_level_keeps_a_hum_soft_and_peaks_below_clipping():
    hum = level(tone(0.5, 0.005), SR)
    assert rms_db(hum) < TARGET_DB - 5, f"boosted by at most {MAX_GAIN_DB} dB"
    spiky = tone(1.0, 0.05)
    spiky[100] = 1.0
    assert np.max(np.abs(level(spiky, SR))) <= PEAK + 1e-6


def test_pause_fits_how_the_piece_ended():
    assert pause_after("And that's it.") == SENTENCE_PAUSE_S
    assert pause_after('He said "no!"') == SENTENCE_PAUSE_S
    assert pause_after("Well, first,") == CLAUSE_PAUSE_S
    assert pause_after("just don't make me so") == RUN_ON_PAUSE_S
    assert SENTENCE_PAUSE_S < 0.4 and CLAUSE_PAUSE_S < 0.2, "OmniVoice's own padding was 0.4 s at every join"


def test_shape_of_an_empty_clip_is_empty():
    assert len(shape(np.zeros(0, np.float32), SR)) == 0


class SlowVoice(FakeVoice):
    """Takes `delay_s` for every piece after the first. Blocks the loop, so loop time moves on with it."""

    def __init__(self, delay_s: float):
        super().__init__()
        self.delay_s = delay_s

    def synthesize(self, text: str):
        if self.spoken:
            time.sleep(self.delay_s)
        return super().synthesize(text)


def test_a_late_piece_counts_its_wait_towards_the_pause():
    s = Stack(voice=SlowVoice(0.5))

    async def run():
        await s.speaker.say("Hello there, my good old friend. How are you?", Emotion.NEUTRAL)

    asyncio.run(run())
    first = 10 * len("Hello there, my good old friend.")  # 0.32 s at the fake's 1 kHz
    pause = s.output.fed[1] - 10 * len("How are you?")
    assert s.output.fed[0] == first
    assert pause < SENTENCE_PAUSE_S * FakeVoice.sample_rate - 100, "0.18 s of the pause went by while waiting"
