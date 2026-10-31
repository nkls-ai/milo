"""The pyannote call diarizer, with a stand-in for the `pyannote.audio` package: what it is given, what it gives back,
and that nothing about a call is reported to pyannote.ai."""

import os
import sys
import types

import numpy as np
import pytest

from milo.adapters.diarize.pyannote import PyannoteDiarizer, PyannoteOptions
from milo.core.registry import ConfigError


class Turn:
    def __init__(self, start, end):
        self.start, self.end = start, end


class Annotation:
    def __init__(self, tracks):
        self.tracks = tracks

    def __bool__(self):
        return bool(self.tracks)

    def itertracks(self, yield_label=False):
        return iter([(Turn(a, b), "_", label) for a, b, label in self.tracks])


class FakePipeline:
    def __init__(self):
        self.inputs, self.device = [], None
        self.reporting_on_load = None

    def to(self, device):
        self.device = device

    def __call__(self, file):
        self.inputs.append(file)
        return types.SimpleNamespace(
            speaker_diarization=Annotation([(0.0, 2.0, "SPEAKER_00"), (1.5, 4.0, "SPEAKER_01")]),
            exclusive_speaker_diarization=Annotation([(0.0, 1.5, "SPEAKER_00"), (1.5, 4.0, "SPEAKER_01")]))


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    made = FakePipeline()

    class Pipeline:
        @staticmethod
        def from_pretrained(folder):
            made.folder = folder
            made.reporting_on_load = os.environ.get("PYANNOTE_METRICS_ENABLED")
            return made

    torch = types.SimpleNamespace(
        from_numpy=lambda a: types.SimpleNamespace(unsqueeze=lambda dim: a[None, :]),
        device=lambda name: name,
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: True)),
        cuda=types.SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "pyannote", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "pyannote.audio", types.SimpleNamespace(Pipeline=Pipeline))
    monkeypatch.delenv("PYANNOTE_METRICS_ENABLED", raising=False)
    (tmp_path / "config.yaml").write_text("pipeline: {}")
    return made, tmp_path


def test_the_whole_track_goes_in_as_a_waveform_and_one_voice_at_a_time_comes_back(pipeline):
    made, folder = pipeline
    diarizer = PyannoteDiarizer(PyannoteOptions(model_dir=str(folder)))
    audio = np.zeros(16000 * 4, np.float32)
    assert diarizer.segments(audio) == [(0.0, 1.5, "SPEAKER_00"), (1.5, 4.0, "SPEAKER_01")], \
        "the exclusive turns, which fit a transcript's lines"
    [given] = made.inputs
    assert given["sample_rate"] == 16000 and given["waveform"].shape == (1, len(audio)), "no file for it to decode"
    assert made.device == "mps", "the GPU when there is one"


def test_usage_reporting_is_off_before_pyannote_loads(pipeline):
    made, folder = pipeline
    PyannoteDiarizer(PyannoteOptions(model_dir=str(folder))).warm()
    assert made.reporting_on_load == "false"


def test_without_the_model_it_says_where_it_should_be(pipeline, tmp_path):
    with pytest.raises(RuntimeError, match="gated"):
        PyannoteDiarizer(PyannoteOptions(model_dir=str(tmp_path / "nowhere"))).warm()


def test_less_than_a_second_of_call_is_nobody(pipeline):
    made, folder = pipeline
    assert PyannoteDiarizer(PyannoteOptions(model_dir=str(folder))).segments(np.zeros(8000, np.float32)) == []
    assert not made.inputs


def test_an_unknown_device_is_a_config_error():
    with pytest.raises(ConfigError, match="device"):
        PyannoteOptions(device="tpu")
