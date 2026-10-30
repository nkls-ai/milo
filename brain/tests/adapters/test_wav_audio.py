import asyncio
import json
import wave

import numpy as np

from milo.adapters.audio.wav_file import WavMicrophone, WavPlayer, read_wav, write_wav
from milo.core.types import STT_SAMPLE_RATE


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_the_file_is_what_a_sound_card_would_have_played_gaps_included(tmp_path):
    clock = Clock()
    player = WavPlayer(tmp_path, clock=clock)

    async def run():
        player.begin(1000, lambda level: None)
        player.feed(np.full(1000, 0.5, np.float32))  # 1 s, plays from 0 to 1
        clock.now += 1.5
        player.feed(np.full(500, 0.25, np.float32))  # fed late: half a second of silence before it
        clock.now += 1.0
        return await player.drain()

    assert asyncio.run(run()) is True
    audio, rate = read_wav(tmp_path / "001.wav")
    assert rate == 1000 and len(audio) == 2000
    assert np.all(audio[1000:1500] == 0) and abs(audio[1600] - 0.25) < 1e-3
    meta = json.loads((tmp_path / "001.json").read_text())
    assert [p["start_s"] for p in meta["pieces"]] == [0.0, 1.5] and meta["interrupted"] is False


def test_interrupt_cuts_the_file_where_playback_was(tmp_path):
    clock = Clock()
    player = WavPlayer(tmp_path, clock=clock)

    async def run():
        player.begin(1000, lambda level: None)
        player.feed(np.full(3000, 0.5, np.float32))
        clock.now += 1.2
        player.interrupt()
        return await player.drain()

    assert asyncio.run(run()) is True, "the stream was already closed: nothing left to drain"
    assert len(read_wav(tmp_path / "001.wav")[0]) == 1200
    assert json.loads((tmp_path / "001.json").read_text())["interrupted"] is True


def test_the_microphone_hears_the_file_in_real_time(tmp_path):
    path = tmp_path / "mic.wav"
    write_wav(path, np.full(STT_SAMPLE_RATE, 0.1, np.float32), STT_SAMPLE_RATE)
    clock = Clock()
    mic = WavMicrophone(path, clock=clock)
    mic.start(lambda level: None)
    clock.now += 0.5
    assert len(mic.peek()) == STT_SAMPLE_RATE // 2
    clock.now += 1.0
    heard = mic.stop()
    assert len(heard) == int(1.5 * STT_SAMPLE_RATE) and heard[-1] == 0, "silence after the file ends"
    assert not mic.active
