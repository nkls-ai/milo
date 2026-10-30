import numpy as np
import pytest

from milo.adapters.stt.mlx_whisper import MlxWhisper, is_hallucination, is_silent
from milo.core.registry import TRANSCRIBERS


@pytest.mark.parametrize("text", ["Thank you.", "thanks for watching!", "Untertitel im Auftrag des ZDF, 2021", "you"])
def test_hallucinations(text):
    assert is_hallucination(text)


def test_real_text_is_not_hallucination():
    assert not is_hallucination("Thank you for the review, merge it")


def test_silence_detection():
    assert is_silent(np.zeros(16000, dtype=np.float32))
    assert is_silent(np.full(1000, 0.5, dtype=np.float32))  # too short
    noise = (np.random.default_rng(1).standard_normal(16000) * 0.05).astype(np.float32)
    assert not is_silent(noise)


def test_factory_maps_options(ctx):
    stt = TRANSCRIBERS.create("mlx_whisper", {"model": "m", "language": "", "vocabulary": "Milo, Codex"}, ctx)
    assert isinstance(stt, MlxWhisper)
    assert (stt.model, stt.language, stt.prompt) == ("m", None, "Milo, Codex")
    assert stt.preview_model == "mlx-community/whisper-base-mlx"
    assert TRANSCRIBERS.create("mlx_whisper", {"model": "m", "preview_model": ""}, ctx).preview_model == "m"
    assert TRANSCRIBERS.create("mlx_whisper", {"language": "de"}, ctx).language == "de"


def test_transcribe_skips_silence_and_hallucinations(monkeypatch):
    outputs = iter(["Thank you.", "Ship it"])
    calls = []
    monkeypatch.setattr(MlxWhisper, "_run", lambda self, audio, model: calls.append(len(audio)) or next(outputs))
    stt = MlxWhisper("m")
    speech = (np.random.default_rng(2).standard_normal(16000) * 0.05).astype(np.float32)
    assert stt.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert calls == []  # silence never reaches Whisper
    assert stt.transcribe(speech) == ""
    assert stt.transcribe(speech) == "Ship it"


def test_preview_uses_the_preview_model(monkeypatch):
    models = []
    monkeypatch.setattr(MlxWhisper, "_run", lambda self, audio, model: models.append(model) or "hi")
    stt = MlxWhisper("big", preview_model="small")
    speech = (np.random.default_rng(3).standard_normal(16000) * 0.05).astype(np.float32)
    assert (stt.transcribe(speech), stt.preview(speech)) == ("hi", "hi")
    assert models == ["big", "small"]
