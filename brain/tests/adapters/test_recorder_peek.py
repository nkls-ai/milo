import numpy as np

from milo.adapters.audio.sounddevice_io import Recorder, tail_of


def test_tail_of_copies_only_from_start_on():
    chunks = [np.arange(0, 4, dtype=np.float32), np.arange(4, 8, dtype=np.float32), np.arange(8, 10, dtype=np.float32)]
    assert tail_of(chunks, 0).tolist() == list(range(10))
    assert tail_of(chunks, 5).tolist() == [5, 6, 7, 8, 9]
    assert tail_of(chunks, 8).tolist() == [8, 9]
    assert tail_of(chunks, 10).tolist() == []
    assert tail_of(chunks, 99).tolist() == []
    assert tail_of([], 0).tolist() == []


def test_an_idle_recorder_peeks_nothing():
    assert len(Recorder().peek()) == 0
