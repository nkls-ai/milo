"""Exercise the local engine contract without downloading weights or needing a GPU."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from milo.adapters.stt.faster_whisper import FasterWhisper, FasterWhisperOptions
from milo.core.meetings import TimedWord
from milo.core.ports import TimedTranscriber, Transcriber, Vocabulary
from milo.core.types import Interrupted
from milo.core.registry import ConfigError


@pytest.fixture
def gpu(monkeypatch):
    """Which device "auto" finds: none by default, so no test needs or touches a GPU."""
    state = {"why": "no NVIDIA GPU"}
    monkeypatch.setattr("milo.adapters.stt.faster_whisper.cuda_unavailable", lambda: state["why"])
    return state


@pytest.fixture
def models(monkeypatch, gpu):
    calls = []

    class Model:
        def __init__(self, name, **options):
            self.name, self.options = name, options
            self.calls = []
            self.segments = [SimpleNamespace(text=" Hello Milo.", compression_ratio=1,
                                             no_speech_prob=0, avg_logprob=-0.1,
                                             words=[SimpleNamespace(start=0.2, end=0.5, word=" Hello")])]
            self.info = SimpleNamespace(language="en", language_probability=0.99)
            calls.append(self)

        def transcribe(self, audio, **options):
            self.calls.append((audio, options))
            return iter(self.segments), self.info

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    return calls


@pytest.fixture
def speech():
    return np.full(16000, 0.1, dtype=np.float32)


def test_construction_is_lazy_and_implements_all_speech_ports(models):
    engine = FasterWhisper()
    assert not models
    assert isinstance(engine, (Transcriber, TimedTranscriber, Vocabulary))
    engine.warm()
    engine.warm()
    assert [model.name for model in models] == ["small", "base"]
    assert models[0].options == {"device": "cpu", "compute_type": "int8", "cpu_threads": 0}
    assert all(len(model.calls) == 1 for model in models), "warm runs each model once"


def test_auto_takes_the_gpu_with_its_own_models(models, gpu, speech):
    gpu["why"] = ""
    engine = FasterWhisper()
    engine.preview(speech)
    engine.transcribe(speech)
    assert [(m.name, m.options["device"], m.options["compute_type"]) for m in models] == [
        ("small", "cuda", "int8_float16"), ("large-v3-turbo", "cuda", "int8_float16")]


def test_a_gpu_that_fails_to_load_falls_back_to_the_cpu(models, gpu, speech, monkeypatch):
    gpu["why"] = ""
    import sys
    model_class = sys.modules["faster_whisper"].WhisperModel

    def picky(name, **options):
        if options["device"] == "cuda":
            raise RuntimeError("CUDA failed with error out of memory")
        return model_class(name, **options)

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=picky))
    engine = FasterWhisper()
    assert engine.transcribe(speech) == "Hello Milo."
    assert (models[-1].name, models[-1].options["device"]) == ("small", "cpu")


def test_explicit_cpu_choice_is_kept_and_gpu_types_never_reach_the_cpu(models, gpu):
    gpu["why"] = ""
    engine = FasterWhisper("medium", device="cpu", compute_type="float16")
    engine.warm()
    assert (models[0].name, models[0].options["device"], models[0].options["compute_type"]) == ("medium", "cpu", "int8")


def test_previews_reuse_the_language_the_full_model_heard(models, speech):
    engine = FasterWhisper()
    engine.transcribe(speech)
    engine.preview(speech)
    assert models[-1].name == "base" and models[-1].calls[-1][1]["language"] == "en"


@pytest.mark.parametrize("options", [{"device": "mps"}, {"model": ""}, {"cpu_threads": -1},
                                    {"cpu_threads": "4"}, {"cpu_threads": True}, {"language": 2}])
def test_invalid_options_fail_before_model_download(options):
    with pytest.raises(ConfigError, match=r"\[stt.faster_whisper\]"):
        FasterWhisperOptions(**options)


def test_silence_never_loads_a_model(models):
    engine = FasterWhisper()
    assert engine.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert engine.preview(np.ones(100, dtype=np.float32)) == ""
    assert engine.words(np.zeros(16000, dtype=np.float32)) == []
    assert engine.spoken_language(np.zeros(16000, dtype=np.float32)) == ""
    assert not models


def test_preview_uses_small_model_without_lowering_final_accuracy(models, speech):
    engine = FasterWhisper()
    assert engine.preview(speech) == "Hello Milo."
    assert engine.transcribe(speech) == "Hello Milo."
    assert [m.name for m in models] == ["base", "small"]
    assert [m.calls[0][1]["beam_size"] for m in models] == [1, 5]
    assert engine.heard_language == "en"


def test_learned_names_are_prompt_data_and_do_not_copy_previous_speech(models, speech):
    engine = FasterWhisper(vocabulary="Milo", language="de")
    engine.use_vocabulary(["Milo", " Anna  Berg ", "Anna Berg"])
    engine.transcribe(speech, before="unrelated text")
    options = models[0].calls[0][1]
    assert options["initial_prompt"] == "Milo, Anna Berg"
    assert options["condition_on_previous_text"] is False
    assert options["language"] == "de"


def test_short_continuation_keeps_detected_language(models, speech):
    engine = FasterWhisper()
    engine.transcribe(speech)
    engine.transcribe(speech, before="Hello")
    assert models[0].calls[-1][1]["language"] == "en"


def test_meeting_words_preserve_timing_and_language(models, speech):
    engine = FasterWhisper()
    assert engine.words(speech) == [TimedWord(0.2, 0.5, " Hello", 0, "en")]
    assert models[0].calls[0][1]["word_timestamps"] is True
    assert engine.spoken_language(speech) == "en"
    models[0].info.language_probability = 0.3
    assert engine.spoken_language(speech) == ""


@pytest.mark.parametrize("changes", [
    {"text": "Thanks for watching!"}, {"compression_ratio": 3},
    {"no_speech_prob": 0.8, "avg_logprob": -2},
])
def test_hallucinations_and_low_confidence_noise_are_dropped(models, speech, changes):
    engine = FasterWhisper()
    engine.warm()
    for key, value in changes.items():
        setattr(models[0].segments[0], key, value)
    assert engine.transcribe(speech) == ""


def test_cancellation_is_checked_while_lazy_segments_decode(models, speech):
    engine = FasterWhisper()
    engine.warm()
    model = models[0]

    def transcribe(audio, **options):
        def segments():
            engine.interrupt()
            yield model.segments[0]
        return segments(), model.info

    model.transcribe = transcribe
    with pytest.raises(Interrupted):
        engine.transcribe(speech)
    engine.wake()
    assert not engine._stop.is_set()
