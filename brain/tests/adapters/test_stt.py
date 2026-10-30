import numpy as np
import pytest

from milo.adapters.stt import mlx_whisper
from milo.adapters.stt.mlx_whisper import MlxWhisper, _Whisper, is_hallucination, is_silent, repeats
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
    monkeypatch.setattr(MlxWhisper, "_run", lambda self, audio, model, *_: calls.append(len(audio)) or next(outputs))
    stt = MlxWhisper("m")
    speech = (np.random.default_rng(2).standard_normal(16000) * 0.05).astype(np.float32)
    assert stt.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert calls == []  # silence never reaches Whisper
    assert stt.transcribe(speech) == ""
    assert stt.transcribe(speech) == "Ship it"


def test_preview_uses_the_preview_model(monkeypatch):
    models = []
    monkeypatch.setattr(MlxWhisper, "_run", lambda self, audio, model, *_: models.append(model) or "hi")
    stt = MlxWhisper("big", preview_model="small")
    speech = (np.random.default_rng(3).standard_normal(16000) * 0.05).astype(np.float32)
    assert (stt.transcribe(speech), stt.preview(speech)) == ("hi", "hi")
    assert models == ["big", "small"]


SPEECH = (np.random.default_rng(4).standard_normal(16000 * 2) * 0.05).astype(np.float32)


class FakeWhisper:
    """Stands in for one loaded model: records what each pass got and reports a detected language."""

    def __init__(self, detected: str = "de"):
        self.passes: list[tuple[str | None, str | None]] = []
        self.language: str | None = None
        self.detected = detected

    def run(self, audio, language, prompt):
        self.passes.append((language, prompt))
        self.language = language or self.detected
        return "ok"


def test_the_text_before_a_phrase_goes_into_the_prompt_after_the_vocabulary():
    stt = MlxWhisper("big", vocabulary="Milo, Codex")
    whisper = stt._models["big"] = FakeWhisper()
    stt.transcribe(SPEECH)
    stt.transcribe(SPEECH, before="x" * 300 + " and then we")
    assert whisper.passes[0][1] == "Milo, Codex"
    assert whisper.passes[1][1] == "Milo, Codex " + ("x" * 300 + " and then we")[-200:].strip()


def test_a_short_phrase_that_goes_on_keeps_the_language_of_the_recording():
    stt = MlxWhisper("big")
    whisper = stt._models["big"] = FakeWhisper(detected="de")
    stt.transcribe(np.tile(SPEECH, 3))  # long: detected
    stt.transcribe(SPEECH, before="Hallo Thomas.")  # short and goes on: kept
    stt.transcribe(SPEECH)  # short but a new recording: detected again
    assert [language for language, _ in whisper.passes] == [None, "de", None]
    assert MlxWhisper("big", language="en")._last_language is None


@pytest.mark.parametrize("text", ["Okay. Okay.", "Yes, please. Yes, please.", "I Milo. I Milo.",
                                  "we need to go we need to go home", "the end the end the end"])
def test_whisper_looping_is_caught(text):
    assert repeats(text)


@pytest.mark.parametrize("text", ["Okay.", "Hi Anna, thanks. I looked at it.", "No no, the other one.", "",
                                  "bye bye", "very, very good", "Thanks, thanks a lot"])
def test_real_speech_is_not_looping(text):
    assert not repeats(text)


def test_a_short_pass_that_cant_be_trusted_falls_back_to_full_windows(monkeypatch):
    whisper = _Whisper("m")
    paths = []
    monkeypatch.setattr(_Whisper, "_load", lambda self: object())
    monkeypatch.setattr(_Whisper, "_run_short", lambda self, *a: paths.append("short") or None)
    monkeypatch.setattr(_Whisper, "_run_full", lambda self, *a: paths.append("full") or "text")
    assert whisper.run(SPEECH, None, None) == "text"
    assert paths == ["short", "full"]


def test_long_audio_takes_the_full_path(monkeypatch):
    whisper = _Whisper("m")
    paths = []
    monkeypatch.setattr(_Whisper, "_load", lambda self: object())
    monkeypatch.setattr(_Whisper, "_run_short", lambda self, *a: paths.append("short") or "short")
    monkeypatch.setattr(_Whisper, "_run_full", lambda self, *a: paths.append("full") or "full")
    assert whisper.run(np.zeros(int(16000 * 29.5)), None, None) == "full"
    assert whisper.run(np.zeros(16000 * 29), None, None) == "short"
    assert paths == ["full", "short"]


def test_a_changed_mlx_whisper_turns_the_short_path_off(monkeypatch):
    whisper = _Whisper("m")
    paths = []

    def broken(self, *a):
        paths.append("short")
        raise AttributeError("no _positional_embedding")

    monkeypatch.setattr(_Whisper, "_load", lambda self: object())
    monkeypatch.setattr(_Whisper, "_run_short", broken)
    monkeypatch.setattr(_Whisper, "_run_full", lambda self, *a: paths.append("full") or "text")
    assert whisper.run(SPEECH, None, None) == "text"
    assert whisper.run(SPEECH, None, None) == "text"
    assert paths == ["short", "full", "full"]


def test_the_window_constants_match_what_was_measured():
    assert mlx_whisper.MIN_WINDOW_S == 10.0 and mlx_whisper.PAD_S == 1.0
