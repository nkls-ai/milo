import asyncio
import shutil
import sys
import types
import wave

import numpy as np
import pytest

from milo.adapters.audio.sounddevice_io import Player, Recorder, level_of
from milo.adapters.tts.omnivoice import REF_TEXT, OmniVoiceTTS, SynthesisCancelled
from milo.adapters.tts.say import MacSay
from milo.core.ports import AudioOutput
from milo.core.registry import AUDIO_INPUTS, AUDIO_OUTPUTS, VOICES, ConfigError


@pytest.mark.skipif(shutil.which("say") is None, reason="needs macOS say")
def test_say_produces_audio(ctx):
    voice = VOICES.create("say", {"voice": ""}, ctx)
    assert isinstance(voice, MacSay) and voice.sample_rate == 22_050
    audio = voice.synthesize("Hello from Milo.")
    assert audio.dtype == np.float32 and audio.ndim == 1
    assert len(audio) > 0.3 * voice.sample_rate
    assert np.abs(audio).max() <= 1.0


# ---- omnivoice, with fake omnivoice and torch modules (no model download)


class FakeOmniModel:
    def __init__(self):
        self.generated: list[dict] = []
        self.clones: list[dict] = []
        self.hooks = []
        self.on_step = None  # called before each step, so a test can cancel mid-generation

    @classmethod
    def from_pretrained(cls, name, **kwargs):
        model = cls()
        model.loaded = (name, kwargs)
        return model

    def register_forward_pre_hook(self, hook):
        self.hooks.append(hook)

    def generate(self, **kwargs):
        self.generated.append(kwargs)
        for step in range(kwargs.get("num_step", 1)):
            if self.on_step:
                self.on_step(step)
            for hook in self.hooks:
                hook(self, ())
        return [np.full(24_000, 0.25, dtype=np.float32)]

    def create_voice_clone_prompt(self, **kwargs):
        self.clones.append(kwargs)
        return ("prompt", len(self.clones))


@pytest.fixture
def fake_omnivoice(monkeypatch):
    seeds = []
    torch = types.SimpleNamespace(float16="f16", float32="f32", manual_seed=seeds.append)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "omnivoice", types.SimpleNamespace(OmniVoice=FakeOmniModel))
    return seeds


def test_omnivoice_factory_is_lazy(ctx):
    options = {"device": "cpu", "instruct": "calm", "voice_seed": 3, "ref_audio": "", "ref_text": "", "steps": 12}
    voice = VOICES.create("omnivoice", options, ctx)
    assert isinstance(voice, OmniVoiceTTS) and voice.sample_rate == 24_000
    assert (voice.device, voice.instruct, voice.voice_seed, voice.steps) == ("cpu", "calm", 3, 12)
    assert voice.voice_dir == ctx.state_dir / "voice"
    assert voice._model is None and not voice.voice_dir.exists()


def test_omnivoice_designs_the_voice_once_and_saves_it(tmp_path, fake_omnivoice):
    voice_dir = tmp_path / "state" / "voice"
    voice = OmniVoiceTTS(voice_dir, device="mps", instruct="calm", voice_seed=11, steps=8)
    voice.warm()
    model = voice._model
    assert model.loaded == ("k2-fsa/OmniVoice", {"device_map": "mps", "dtype": "f16"})
    assert fake_omnivoice == [11]
    design, warm_up = model.generated
    assert design == {"text": REF_TEXT, "instruct": "calm", "num_step": 32}
    assert model.clones == [{"ref_audio": str(voice_dir / "ref.wav"), "ref_text": REF_TEXT}]
    assert warm_up["voice_clone_prompt"] == voice._clone_prompt and warm_up["num_step"] == 8
    assert (voice_dir / "ref.txt").read_text().strip() == REF_TEXT
    with wave.open(str(voice_dir / "ref.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24_000, 24_000)
    assert not list(voice_dir.glob("*.tmp"))

    again = OmniVoiceTTS(voice_dir, instruct="something else", voice_seed=99)
    again.warm()
    assert fake_omnivoice == [11]  # reused the saved voice, no second design
    assert [g.get("instruct") for g in again._model.generated] == [None]
    assert again._model.clones == [{"ref_audio": str(voice_dir / "ref.wav"), "ref_text": REF_TEXT}]


def test_omnivoice_ref_audio_overrides_the_designed_voice(tmp_path, fake_omnivoice):
    voice_dir = tmp_path / "voice"
    voice_dir.mkdir()
    (voice_dir / "ref.wav").write_bytes(b"old")
    (voice_dir / "ref.txt").write_text("old")
    clip = tmp_path / "me.wav"
    clip.write_bytes(b"x")

    voice = OmniVoiceTTS(voice_dir, ref_audio=str(clip), ref_text=" Hello, it's me. ")
    voice.warm()
    assert voice._model.clones == [{"ref_audio": str(clip), "ref_text": "Hello, it's me."}]
    assert fake_omnivoice == []

    untranscribed = OmniVoiceTTS(voice_dir, ref_audio=str(clip))
    untranscribed.warm()
    assert untranscribed._model.clones == [{"ref_audio": str(clip), "ref_text": None}]  # OmniVoice's ASR

    with pytest.raises(ConfigError, match="ref_audio not found"):
        OmniVoiceTTS(voice_dir, ref_audio=str(tmp_path / "missing.wav")).warm()


def test_omnivoice_synthesize_always_clones(tmp_path, fake_omnivoice):
    voice = OmniVoiceTTS(tmp_path / "voice", steps=6)
    first = voice.synthesize("Hi.")
    voice.synthesize("Again.")
    assert first.dtype == np.float32 and first.ndim == 1 and len(first) == 24_000
    *_, a, b = voice._model.generated
    assert a == {"text": "Hi.", "voice_clone_prompt": voice._clone_prompt, "num_step": 6}
    assert b == {"text": "Again.", "voice_clone_prompt": voice._clone_prompt, "num_step": 6}
    assert len(voice._model.clones) == 1


def test_omnivoice_cancel_aborts_the_running_synthesis_at_the_next_step(tmp_path, fake_omnivoice):
    voice = OmniVoiceTTS(tmp_path / "voice", steps=6)
    voice.warm()
    voice._model.on_step = lambda step: step == 2 and voice.cancel()
    with pytest.raises(SynthesisCancelled):
        voice.synthesize("A long piece the user talked over.")
    voice._model.on_step = None
    assert len(voice.synthesize("The next one plays.")) == 24_000, "a cancel never leaks into later calls"
    voice.cancel()  # idle: nothing to abort
    assert len(voice.synthesize("Still fine.")) == 24_000


def test_omnivoice_restores_logging_disabled_while_loading(tmp_path, fake_omnivoice, monkeypatch):
    import logging

    def loading(name, **kwargs):
        logging.disable(logging.INFO)
        return FakeOmniModel()

    monkeypatch.setattr(FakeOmniModel, "from_pretrained", staticmethod(loading))
    try:
        OmniVoiceTTS(tmp_path / "voice").warm()
        assert logging.root.manager.disable == logging.NOTSET
    finally:
        logging.disable(logging.NOTSET)


# ---- sounddevice, with a fake module whose stream the test drives by hand


class FakeOutputStream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = self.closed = self.stopped = False
        FakeSd.streams.append(self)

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def pump(self, frames: int = 4) -> np.ndarray:
        """One audio-thread callback. Returns what it wrote; finishes the stream on CallbackStop."""
        out = np.full((frames, 1), 9.0, dtype=np.float32)
        try:
            self.kwargs["callback"](out, frames, None, None)
        except FakeSd.CallbackStop:
            self.stopped = True
            self.kwargs["finished_callback"]()
        return out[:, 0].copy()


class FakeSd:
    streams: list[FakeOutputStream] = []

    class CallbackStop(Exception):
        pass

    OutputStream = FakeOutputStream


@pytest.fixture
def fake_sd(monkeypatch):
    FakeSd.streams = []
    monkeypatch.setitem(sys.modules, "sounddevice", FakeSd)
    return FakeSd


def test_player_streams_chunks_back_to_back_with_silence_on_underrun(fake_sd):
    async def main():
        levels = []
        player = Player(device="Speakers")
        assert isinstance(player, AudioOutput)
        player.begin(16_000, levels.append)
        [stream] = fake_sd.streams
        assert stream.started and stream.kwargs["samplerate"] == 16_000 and stream.kwargs["device"] == "Speakers"
        assert stream.kwargs["channels"] == 1 and stream.kwargs["dtype"] == "float32"

        assert stream.pump().tolist() == [0, 0, 0, 0]  # nothing fed yet: silence, keeps running
        player.feed(np.array([0.1, 0.2, 0.3], dtype=np.float32))
        player.feed(np.array([[0.4], [0.5]]))  # any shape, any dtype
        player.feed(np.zeros(0))
        assert stream.pump() == pytest.approx([0.1, 0.2, 0.3, 0.4])
        assert stream.pump() == pytest.approx([0.5, 0, 0, 0])  # underrun mid-block: padded, not stopped
        assert not stream.stopped
        player.feed(np.array([0.6], dtype=np.float32))

        drain = asyncio.create_task(player.drain())
        await asyncio.sleep(0)
        assert not drain.done()
        assert stream.pump() == pytest.approx([0.6, 0, 0, 0])
        assert stream.stopped
        assert await drain is True
        assert stream.closed and levels[-1] == 0.0 and max(levels) > 0

    asyncio.run(main())


def test_player_plays_the_device_latency_in_silence_before_it_stops(fake_sd, monkeypatch):
    monkeypatch.setattr(FakeOutputStream, "latency", 0.001, raising=False)  # 16 samples at 16 kHz

    async def main():
        player = Player()
        player.begin(16_000, lambda level: None)
        [stream] = fake_sd.streams
        player.feed(np.full(4, 0.5, dtype=np.float32))
        drain = asyncio.create_task(player.drain())
        await asyncio.sleep(0)
        stream.pump()
        pumps = 0
        while not stream.stopped:
            assert stream.pump().tolist() == [0, 0, 0, 0]
            pumps += 1
        assert pumps == 4, "16 samples of silence, so the last word reaches the ear before the stream closes"
        assert await drain is True

    asyncio.run(main())


def test_player_interrupt_drops_audio_and_drain_returns_false(fake_sd):
    async def main():
        levels = []
        player = Player()
        player.begin(24_000, levels.append)
        stream = fake_sd.streams[0]
        player.feed(np.full(100, 0.5, dtype=np.float32))
        drain = asyncio.create_task(player.drain())
        await asyncio.sleep(0)
        player.interrupt()
        assert await asyncio.wait_for(drain, 1) is False
        assert stream.closed and levels[-1] == 0.0
        player.feed(np.ones(10))  # late chunks after an interrupt go nowhere
        assert await player.drain() is True  # nothing open any more

        player.begin(24_000, levels.append)
        player.interrupt()
        assert await player.drain() is False  # drain after interrupt still reports it

    asyncio.run(main())


def test_player_begin_interrupts_an_open_stream(fake_sd):
    async def main():
        player = Player()
        player.begin(24_000, lambda level: None)
        player.feed(np.ones(10, dtype=np.float32))
        player.begin(22_050, lambda level: None)
        old, new = fake_sd.streams
        assert old.closed and not new.closed
        assert new.kwargs["samplerate"] == 22_050
        assert new.pump().tolist() == [0, 0, 0, 0]  # the old stream's audio is gone
        player.feed(np.full(2, 0.5, dtype=np.float32))
        drain = asyncio.create_task(player.drain())
        await asyncio.sleep(0)
        new.pump()
        assert await drain is True

    asyncio.run(main())


def test_sounddevice_registered_for_both_directions_with_shared_table(ctx):
    table = {"input_device": "", "output_device": "MacBook Pro Speakers"}
    rec = AUDIO_INPUTS.create("sounddevice", table, ctx)
    player = AUDIO_OUTPUTS.create("sounddevice", table, ctx)
    assert isinstance(rec, Recorder) and rec.device is None and not rec.active
    assert isinstance(player, Player) and player.device == "MacBook Pro Speakers"
    assert AUDIO_INPUTS.create("sounddevice", {"input_device": 2}, ctx).device == 2


def test_recorder_stop_without_start_is_empty(ctx):
    assert len(Recorder().stop()) == 0


def test_level_of():
    assert level_of(np.zeros(0, dtype=np.float32)) == 0.0
    assert level_of(np.full(10, 0.5, dtype=np.float32)) == 1.0
    assert 0 < level_of(np.full(10, 0.01, dtype=np.float32)) < 1


def test_gpu_decoding_in_windows_matches_one_long_decode():
    torch = pytest.importorskip("torch")
    from milo.adapters.tts._gpu_decode import WindowedDecoder, decode_on_gpu

    spf = 960

    class Tokenizer:
        """Each frame's audio depends on the frames around it, like a convolutional decoder. Like MPS, it
        gets calls producing more than 65,536 samples wrong."""

        device = "cpu"

        def __init__(self, limit=None):
            self.limit = limit
            self.moved = False

        def to(self, device):
            self.device, self.moved = device, True

        def decode(self, codes):
            c = codes[0, 0].double()
            near = torch.stack([torch.roll(c, k) for k in range(-3, 4)]).mean(0)
            near[:3], near[-3:] = c[:3], c[-3:]
            audio = (torch.sin(near[:, None] * torch.arange(spf) / 50)).reshape(1, 1, -1)
            if self.moved and self.limit and audio.shape[-1] > self.limit:
                audio = audio * 0
            return types.SimpleNamespace(audio_values=audio)

    codes = torch.randint(0, 1000, (1, 8, 150))
    whole = Tokenizer().decode(codes).audio_values
    gpu = Tokenizer(limit=65_536)
    gpu.to("gpu")
    assert not torch.allclose(gpu.decode(codes).audio_values, whole), "the fake gets long calls wrong"
    windowed = WindowedDecoder(gpu.decode, torch, spf)(codes).audio_values
    assert windowed.shape == whole.shape
    inner = slice(3 * spf, -3 * spf)  # the fake's own edges aren't convolutional
    assert torch.allclose(windowed[..., inner].double(), whole[..., inner])

    # "cpu" stands in for the GPU here, so the test runs anywhere; the limit is what makes it MPS-like.
    model = types.SimpleNamespace(audio_tokenizer=Tokenizer(limit=65_536))
    assert decode_on_gpu(model, codes[0, :, :49], torch, "cpu")
    assert isinstance(model.audio_tokenizer.decode, WindowedDecoder)

    broken = types.SimpleNamespace(audio_tokenizer=Tokenizer())
    broken.audio_tokenizer.decode = lambda c: types.SimpleNamespace(audio_values=torch.rand(1, 1, c.shape[-1] * spf))
    assert not decode_on_gpu(broken, codes[0, :, :49], torch, "cpu"), "a decoder that disagrees stays on the CPU"
    assert not isinstance(broken.audio_tokenizer.decode, WindowedDecoder)
