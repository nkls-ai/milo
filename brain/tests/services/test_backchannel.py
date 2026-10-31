import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from milo.core.types import Emotion
from milo.services import backchannel
from milo.services.backchannel import CLIPS, Backchannel
from milo.services.speaker import Speaker
from milo.services.ui_state import UiState
from tests.fakes import FakeAudioOutput, FakeLiveModel, FakeVoice, RecordingSink
from tests.services.stack import Stack, settle

LATE_S = 0.05


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(backchannel, "LATE_S", LATE_S)
    monkeypatch.setattr(backchannel, "QUEUE_S", 0.0)


def stack(model: FakeLiveModel, voice: FakeVoice | None = None, enabled: bool = True) -> tuple[Stack, Backchannel]:
    """A conversation that has had its first turn already: the first turn never gets a backchannel."""
    model.script.appendleft(["[happy] Yes?"])
    s = Stack(model=model, voice=voice or FakeVoice())
    chan = Backchannel(s.speaker, enabled=enabled)
    chan.warm()
    s.live_talk._backchannel = chan
    gate, model.gate = model.gate, None

    async def first():
        await s.live_talk.start("are you there")

    asyncio.run(first())
    model.gate = gate
    s.voice.spoken.clear()
    s.output.streams.clear()
    return s, chan


def test_a_late_reply_starts_with_one_backchannel_on_the_same_stream():
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "] Sure, it is nine."], gate=gate))

    async def run():
        turn = s.live_talk.start("what time is it")
        await asyncio.sleep(LATE_S * 4)
        assert chan.played == 1 and s.speaker.active, "Hm. while the model still thinks"
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 1
    assert s.voice.spoken == ["Sure, it is nine."], "the clip was rendered at warm-up, not now"
    assert len(s.output.streams) == 1 and len(s.output.fed) >= 2, "the clip and the answer share one stream"
    assert s.bubbles()[-1] == "Sure, it is nine.", "the clip isn't shown"


def test_a_quick_reply_has_none_and_they_never_repeat_back_to_back():
    s, chan = stack(FakeLiveModel(["[happy] Sure."], ["[happy", "] Fine."], ["[happy] Ok."]))
    gate = asyncio.Event()

    async def run():
        await s.live_talk.start("hi")
        assert chan.played == 0, "it answered in time"
        s.model.gate = gate
        turn = s.live_talk.start("and now?")
        await asyncio.sleep(LATE_S * 4)
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 1


def test_one_per_cooldown_and_the_next_one_is_a_different_clip(monkeypatch):
    monkeypatch.setattr(backchannel, "COOLDOWN_S", 0.0)
    s, chan = stack(FakeLiveModel(["[happy", "] One."], ["[happy", "] Two."]))
    picked = []

    async def run():
        for text in ("one", "two"):
            gate = asyncio.Event()
            s.model.gate = gate
            turn = s.live_talk.start(text)
            await asyncio.sleep(LATE_S * 4)
            picked.append(chan._last)
            gate.set()
            await turn

    asyncio.run(run())
    assert picked == [CLIPS[0], CLIPS[1]]


def test_a_cooldown_keeps_the_second_late_reply_quiet():
    s, chan = stack(FakeLiveModel(["[happy", "] One."], ["[happy", "] Two."]))

    async def run():
        for text in ("one", "two"):
            gate = asyncio.Event()
            s.model.gate = gate
            turn = s.live_talk.start(text)
            await asyncio.sleep(LATE_S * 4)
            gate.set()
            await turn

    asyncio.run(run())
    assert chan.played == 1


def test_a_silent_reply_finishes_the_backchannel_and_milo_rests():
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "]"], gate=gate))

    async def run():
        turn = s.live_talk.start("remember that")
        await asyncio.sleep(LATE_S * 4)
        assert chan.played == 1
        gate.set()
        await turn
        await settle()
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert not s.speaker.active, "the clip played out and nothing hangs"


def test_off_means_off():
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "] Sure."], gate=gate), enabled=False)

    async def run():
        turn = s.live_talk.start("hi")
        await asyncio.sleep(LATE_S * 4)
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 0 and s.voice.spoken == ["Sure."]


def test_held_milo_says_nothing():
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "] Sure."], gate=gate))

    async def run():
        turn = s.live_talk.start("hi")
        await settle()
        s.speaker.hold()  # the user pressed the talk key while he thinks
        await asyncio.sleep(LATE_S * 4)
        assert chan.played == 0
        s.speaker.resume()
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 0


def test_with_the_voice_off_there_is_no_hm_either():
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "] Sure."], gate=gate))
    s.speaker.silent = True

    async def run():
        turn = s.live_talk.start("hi")
        await asyncio.sleep(LATE_S * 4)
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 0 and s.voice.spoken == []


def test_no_backchannel_once_the_first_text_is_in_even_if_the_voice_is_slow():
    """The misfire: "Hm." landing a moment before the answer, because text was in but its audio wasn't yet."""
    class SlowVoice(FakeVoice):
        def synthesize(self, text):
            if text not in CLIPS:
                time.sleep(LATE_S * 6)
            return super().synthesize(text)

    output = FakeAudioOutput()
    with ThreadPoolExecutor(1) as tts:
        speaker = Speaker(SlowVoice(), output, UiState(RecordingSink()), tts)
        chan = Backchannel(speaker)
        chan.warm()

        async def run():
            chan.arm("what time is it")
            u = chan.utterance(Emotion.HAPPY)
            u.add("Sure, it is nine.")
            chan.release()  # the text is all in; the first piece is still synthesizing
            assert await u.finish() is True

        asyncio.run(run())
    assert chan.played == 0
    assert len(output.streams) == 1


def test_text_arriving_while_the_clip_is_queued_cancels_it(monkeypatch):
    monkeypatch.setattr(backchannel, "QUEUE_S", LATE_S * 4)
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "] Sure, it is nine."], gate=gate))

    async def run():
        turn = s.live_talk.start("what time is it")
        await asyncio.sleep(LATE_S * 2)  # past the deadline, the clip waits in the queue
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 0 and s.voice.spoken == ["Sure, it is nine."]


def test_never_on_a_conversations_first_turn():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy", "] Sure, it is nine."], gate=gate))
    chan = Backchannel(s.speaker)
    chan.warm()
    s.live_talk._backchannel = chan

    async def run():
        turn = s.live_talk.start("what time is it")
        await asyncio.sleep(LATE_S * 4)
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 0


@pytest.mark.parametrize("greeting", ["Hey, Milo", "hi milo, how are you?", "Guten Morgen!", "Hallo Milo"])
def test_never_on_a_greeting(greeting):
    gate = asyncio.Event()
    s, chan = stack(FakeLiveModel(["[happy", "] Hi!"], gate=gate))

    async def run():
        turn = s.live_talk.start(greeting)
        await asyncio.sleep(LATE_S * 4)
        gate.set()
        await turn

    asyncio.run(run())
    assert chan.played == 0


def test_what_a_greeting_is():
    from milo.services.backchannel import is_greeting

    assert is_greeting("Hey, Milo.") and is_greeting("Moin") and is_greeting("good morning milo")
    assert not is_greeting("Hey Milo, set a timer for ten minutes please")
    assert not is_greeting("what time is it") and not is_greeting("")


def test_clips_are_rendered_once_per_voice_and_kept(tmp_path):
    """Every start rendered the four clips again; with a paid voice each start cost credits."""
    class PaidVoice(FakeVoice):
        clip_key = "elevenlabs v4 milo"

    voice = PaidVoice()
    speaker = SimpleNamespace(voice=voice)  # all warm() reads
    Backchannel(speaker, cache=tmp_path).warm()
    assert voice.spoken == list(CLIPS)
    again = Backchannel(speaker, cache=tmp_path)
    again.warm()
    assert voice.spoken == list(CLIPS), "the next start renders nothing"
    assert set(again._clips) == set(CLIPS)

    voice.clip_key = "elevenlabs v4 another voice"
    Backchannel(speaker, cache=tmp_path).warm()
    assert voice.spoken == list(CLIPS) * 2, "another voice gets its own"

    standing_in = FakeVoice()  # the fallback, or a voice that says nothing about itself: never kept
    Backchannel(SimpleNamespace(voice=standing_in), cache=tmp_path / "x").warm()
    assert not (tmp_path / "x").exists()
