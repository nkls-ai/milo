"""Pocket TTS, with a stand-in for the `pocket_tts` package: which model speaks a piece, and stopping one."""

import asyncio
import sys
import threading
import types

import numpy as np
import pytest

from milo.adapters.tts.pocket import PocketTTS, SynthesisCancelled


class FakeModel:
    sample_rate = 24_000

    def __init__(self, language: str):
        self.language = language
        self.spoken: list[str] = []
        self.voices: list[str] = []
        self.started = threading.Event()
        self.hold = False

    def get_state_for_audio_prompt(self, voice: str):
        self.voices.append(voice)
        return {"voice": voice}

    def generate_audio(self, state, text: str):
        self.spoken.append(text)

    def generate_audio_stream(self, state, text: str, stop: threading.Event | None = None):
        self.spoken.append(text)
        self.started.set()
        while self.hold and not stop.is_set():
            stop.wait(0.01)
        if stop is not None and stop.is_set():
            return
        yield FakeTensor(len(text))


class FakeTensor:
    def __init__(self, n: int):
        self.n = n

    def numpy(self):
        return np.full(self.n, 0.1, dtype=np.float32)


@pytest.fixture
def models(monkeypatch):
    made: dict[str, FakeModel] = {}

    class TTSModel:
        @staticmethod
        def load_model(language: str):
            made[language] = FakeModel(language)
            return made[language]

    monkeypatch.setitem(sys.modules, "pocket_tts", types.SimpleNamespace(TTSModel=TTSModel))
    return made


def test_each_piece_goes_to_the_model_of_its_language_with_the_same_voice(models):
    voice = PocketTTS(voice="stuart_bell")
    voice.warm()
    assert set(models) == {"english", "german"}
    assert models["english"].voices == models["german"].voices == ["stuart_bell"]
    assert len(voice.synthesize("Opening YouTube in Chrome.")) == len("Opening YouTube in Chrome.")
    voice.synthesize("Es ist jetzt halb acht.")
    voice.synthesize("Okay.")  # too short to tell: the language before
    assert models["english"].spoken[1:] == ["Opening YouTube in Chrome."], "the first one warmed it up"
    assert models["german"].spoken[1:] == ["Es ist jetzt halb acht.", "Okay."]


def test_without_a_german_model_everything_is_english(models):
    voice = PocketTTS(german="")
    voice.synthesize("Es ist jetzt halb acht.")
    assert set(models) == {"english"} and models["english"].spoken[-1] == "Es ist jetzt halb acht."


def test_cancel_stops_a_piece_being_spoken(models):
    voice = PocketTTS()
    voice.warm()
    models["english"].hold = True
    errors = []

    def speak():
        try:
            voice.synthesize("This is a long answer that the user talks over.")
        except SynthesisCancelled as e:
            errors.append(e)

    thread = threading.Thread(target=speak)
    thread.start()
    assert models["english"].started.wait(2)
    voice.cancel()
    thread.join(2)
    assert errors and not thread.is_alive()
    models["english"].hold = False
    assert len(voice.synthesize("And the next one is spoken.")) > 0, "one started afterwards is unaffected"


def test_without_the_extra_it_says_what_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pocket_tts", None)
    with pytest.raises(RuntimeError, match="pocket"):
        PocketTTS().warm()


def test_a_stream_hands_each_piece_over_as_it_is_made_then_ends(models):
    voice = PocketTTS()

    async def run():
        voice.warm()
        stream = voice.stream()
        stream.send("Opening YouTube.")
        stream.send("Es ist halb acht.")
        stream.finish()
        return [(i, len(audio)) async for i, audio in stream]

    got = asyncio.run(run())
    assert got == [(0, len("Opening YouTube.")), (0, 0), (1, len("Es ist halb acht.")), (1, 0)], \
        "the audio, then an empty mark for each piece"
    assert models["german"].spoken[-1] == "Es ist halb acht."


def test_a_cancelled_stream_ends_and_the_voice_can_go_on(models):
    voice = PocketTTS()
    voice.warm()
    models["english"].hold = True

    async def run():
        stream = voice.stream()
        stream.send("A long answer the user talks over.")
        await asyncio.to_thread(models["english"].started.wait, 2)
        voice.cancel()  # barge-in cancels the voice, which stops its streams
        return [item async for item in stream]

    assert asyncio.run(run()) == []
    models["english"].hold = False
    assert len(voice.synthesize("Next.")) > 0
