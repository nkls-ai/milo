import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

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
    monkeypatch.setattr(backchannel, "SOON_S", 0.0)


def stack(model: FakeLiveModel, voice: FakeVoice | None = None, enabled: bool = True) -> tuple[Stack, Backchannel]:
    s = Stack(model=model, voice=voice or FakeVoice())
    chan = Backchannel(s.speaker, enabled=enabled)
    chan.warm()
    s.voice.spoken.clear()
    s.live_talk._backchannel = chan
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
    s, chan = stack(FakeLiveModel(["[happy] Sure."], ["[happy] Fine."], ["[happy] Ok."]))
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
    s, chan = stack(FakeLiveModel(["[happy] One."], ["[happy] Two."]))
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
    s, chan = stack(FakeLiveModel(["[happy] One."], ["[happy] Two."]))

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


def test_a_first_piece_still_synthesizing_gets_a_backchannel_ahead_of_it():
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
            chan.arm()
            u = chan.utterance(Emotion.HAPPY)
            u.add("Sure, it is nine.")
            chan.release()  # the text is all in; the first piece is still synthesizing
            assert await u.finish() is True

        asyncio.run(run())
    assert chan.played == 1
    assert output.fed[0] == len(chan._clips[CLIPS[0]]), "the clip went out first"
    assert len(output.streams) == 1
