import threading

import numpy as np
import pytest

from milo.adapters.stt import mlx_whisper
from milo.adapters.stt.mlx_whisper import MlxWhisper, _Whisper, is_hallucination, is_silent, repeats
from milo.core.registry import TRANSCRIBERS
from milo.core.types import Interrupted


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
        self.passes: list[tuple[str | None, str | None, bool]] = []
        self.language: str | None = None
        self.detected = detected

    def run(self, audio, language, prompt, *, quick=False):
        self.passes.append((language, prompt, quick))
        self.language = language or self.detected
        return "ok"


def test_only_the_vocabulary_goes_into_the_prompt_and_quick_passes_say_so():
    stt = MlxWhisper("big", vocabulary="Milo, Codex")
    whisper = stt._models["big"] = FakeWhisper()
    stt.transcribe(SPEECH)
    stt.transcribe(SPEECH, before="and then we", quick=True)
    assert whisper.passes == [(None, "Milo, Codex", False), ("de", "Milo, Codex", True)]


def test_a_short_phrase_that_goes_on_keeps_the_language_of_the_recording():
    stt = MlxWhisper("big")
    whisper = stt._models["big"] = FakeWhisper(detected="de")
    stt.transcribe(np.tile(SPEECH, 3))  # long: detected
    stt.transcribe(SPEECH, before="Hallo Thomas.")  # short and goes on: kept
    stt.transcribe(SPEECH)  # short but a new recording: detected again
    assert [language for language, _, _ in whisper.passes] == [None, "de", None]
    assert MlxWhisper("big", language="en")._last_language is None


@pytest.mark.parametrize("text", ["Okay. Okay.", "Yes, please. Yes, please.", "I Milo. I Milo.",
                                  "we need to go we need to go home", "the end the end the end",
                                  "Erinnere mich heute Abend um 8 Uhr um 8 Uhr die Blumen zu gießen."])
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
    assert whisper.run(SPEECH, None, None, quick=True) == "text"
    assert paths == ["short", "full"]
    assert whisper.run(SPEECH, None, None) == "text"
    assert paths == ["short", "full", "full"], "a pass nobody waits for takes the accurate path"


def test_long_audio_takes_the_full_path(monkeypatch):
    whisper = _Whisper("m")
    paths = []
    monkeypatch.setattr(_Whisper, "_load", lambda self: object())
    monkeypatch.setattr(_Whisper, "_run_short", lambda self, *a: paths.append("short") or "short")
    monkeypatch.setattr(_Whisper, "_run_full", lambda self, *a: paths.append("full") or "full")
    assert whisper.run(np.zeros(int(16000 * 29.5)), None, None, quick=True) == "full"
    assert whisper.run(np.zeros(16000 * 29), None, None, quick=True) == "short"
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
    assert whisper.run(SPEECH, None, None, quick=True) == "text"
    assert whisper.run(SPEECH, None, None, quick=True) == "text"
    assert paths == ["short", "full", "full"]


def test_the_window_constants_match_what_was_measured():
    assert mlx_whisper.MIN_WINDOW_S == 10.0 and mlx_whisper.PAD_S == 1.0


class FakeMlxEncoder:
    """The parts of mlx_whisper's AudioEncoder that _Encoder uses: identity convolutions, 8 blocks that
    count how often they ran."""

    def __init__(self):
        import mlx.core as mx

        self.ran = 0
        self._positional_embedding = mx.zeros((1500, 4))
        self.conv1 = self.conv2 = self.ln_post = lambda x: x
        self.blocks = [self._block] * 8

    def _block(self, x):
        self.ran += 1
        return x, None, None


def test_an_interrupt_ends_the_encoding_between_layers():
    import mlx.core as mx

    stop = threading.Event()
    inner = FakeMlxEncoder()
    encoder = mlx_whisper._Encoder(inner, 1280, stop)
    mel = mx.zeros((1, 1500, 4))
    assert encoder(mel).shape == (1, 1500, 4) and inner.ran == 8
    assert encoder(mel) is not None and inner.ran == 8, "the same window is encoded once"
    stop.set()
    with pytest.raises(Interrupted):
        encoder(mx.ones((1, 1500, 4)))
    assert inner.ran == 8, "stopped before the first layer"
    assert encoder(mx.zeros((1, 10, 1280))).shape == (1, 10, 1280), "an encoding passes through"


def test_interrupt_reaches_the_pass_and_the_next_pass_starts_clean(monkeypatch):
    stt = MlxWhisper("big")
    seen = []
    monkeypatch.setattr(MlxWhisper, "_run", lambda self, *a: seen.append(self._stop.is_set()) or "ok")
    stt.interrupt()
    assert stt.transcribe(SPEECH) == "ok"
    assert seen == [False], "an interrupt only ends the pass running when it came"


def test_learned_words_follow_the_configured_vocabulary_in_the_prompt():
    stt = MlxWhisper("big", vocabulary="Milo, Codex")
    whisper = stt._models["big"] = FakeWhisper()
    stt.use_vocabulary(["codex", "Claude Code", " Niklas  Dobberstein ", ""])
    stt.transcribe(SPEECH)
    assert whisper.passes[-1][1] == "Milo, Codex, Claude Code, Niklas Dobberstein"
    stt.use_vocabulary([])
    assert stt.prompt == "Milo, Codex"
    assert MlxWhisper("big").prompt is None
    empty = MlxWhisper("big")
    empty.use_vocabulary(["Niklas"])
    assert empty.prompt == "Niklas"


def test_learned_words_in_the_prompt_are_capped():
    prompt = mlx_whisper.vocabulary_prompt("Milo", [f"Word{i:03d}" for i in range(200)])
    learned = prompt.removeprefix("Milo, ")
    assert len(learned) <= mlx_whisper.LEARNED_CHARS
    assert learned.startswith("Word000, Word001")
