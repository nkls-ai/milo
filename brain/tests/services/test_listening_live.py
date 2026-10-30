"""Listening with tentative starts and live transcription ([dictation] stream)."""

import asyncio

from milo.core.events import Dictation, Level, Partial
from milo.core.types import ListenMode, LiveMode, MiloState
from milo.services.listening import Listening
from tests.services.stack import InlineExecutor, Stack, settle
from tests.services.test_live_transcript import GrowingMic, hear, quiet, tone


class HearingStt:
    def __init__(self):
        self.calls: list[int] = []

    def warm(self) -> None:
        pass

    def transcribe(self, audio) -> str:
        self.calls.append(len(audio))
        return hear(audio)


def wired(live: LiveMode) -> tuple[Stack, Listening, GrowingMic, HearingStt]:
    s, mic, stt = Stack(), GrowingMic(), HearingStt()
    mic.active = False
    listening = Listening(mic, stt, InlineExecutor(), s.ui, s.dictation, s.live_talk, s.context, live)
    s.context.update("Notes", 0)
    return s, listening, mic, stt


def test_a_tentative_start_shows_nothing_and_a_cancel_leaves_no_trace():
    s, listening, mic, _ = wired(LiveMode.PREVIEW)

    async def run():
        listening.start(ListenMode.DICTATE, tentative=True)
        mic.say(tone("alpha", 0.3))
        await settle()
        listening.cancel()

    asyncio.run(run())
    assert not mic.active
    assert s.sink.events == [], "no state, no levels, no partials: a tap is invisible"


def test_confirm_shows_the_recording_and_stop_transcribes_it():
    s, listening, mic, stt = wired(LiveMode.OFF)

    async def run():
        listening.start(ListenMode.DICTATE, tentative=True)
        listening.confirm()
        listening.confirm()
        mic.say(tone("alpha", 1))
        await listening.stop()

    asyncio.run(run())
    assert s.states() == [MiloState.DICTATING, MiloState.TRANSCRIBING, MiloState.IDLE]
    assert s.sink.of(Dictation) == [Dictation("ALPHA")]
    assert s.sink.of(Partial) == [] and len(stt.calls) == 1


def test_a_release_before_the_confirm_still_counts():
    s, listening, mic, _ = wired(LiveMode.OFF)

    async def run():
        listening.start(ListenMode.DICTATE, tentative=True)
        mic.say(tone("bravo", 1))
        await listening.stop()

    asyncio.run(run())
    assert s.sink.of(Dictation) == [Dictation("BRAVO")]
    assert s.states() == [MiloState.TRANSCRIBING, MiloState.IDLE]


def test_preview_shows_words_live_and_pastes_one_final_pass_over_everything():
    s, listening, mic, stt = wired(LiveMode.PREVIEW)

    async def run():
        listening.start(ListenMode.DICTATE)
        mic.say(tone("alpha", 1), quiet(1))
        await asyncio.sleep(0.5)
        mic.say(tone("bravo", 1))
        await asyncio.sleep(0.5)
        assert s.sink.of(Dictation) == [], "nothing is pasted before release"
        await listening.stop()

    asyncio.run(run())
    assert "alpha bravo" in [e.text for e in s.sink.of(Partial)]
    assert s.sink.of(Dictation) == [Dictation("ALPHA BRAVO")]
    assert stt.calls[-1] == len(mic.audio), "the final pass covers the whole recording"
    assert s.history.entries == [("ALPHA BRAVO", "Notes")]


def test_type_mode_pastes_at_pauses_and_only_the_tail_on_release():
    s, listening, mic, stt = wired(LiveMode.TYPE)

    async def run():
        listening.start(ListenMode.DICTATE)
        mic.say(tone("alpha", 1), quiet(1))
        await asyncio.sleep(0.5)
        assert s.sink.of(Dictation) == [Dictation("ALPHA")]
        mic.say(tone("bravo", 1), quiet(1), tone("charlie", 0.8))
        await asyncio.sleep(0.5)
        await listening.stop()

    asyncio.run(run())
    assert s.sink.of(Dictation) == [Dictation("ALPHA"), Dictation(" BRAVO"), Dictation(" CHARLIE")]
    assert stt.calls[-1] < 1.5 * 16000, "the final pass covers only the tail"
    assert s.history.entries == [("ALPHA BRAVO CHARLIE", "Notes")]
    assert s.states()[-1] is MiloState.IDLE


def test_talk_shows_a_preview_but_types_nothing():
    s, listening, mic, _ = wired(LiveMode.TYPE)

    async def run():
        listening.start(ListenMode.TALK)
        mic.say(tone("alpha", 1), quiet(1))
        await asyncio.sleep(0.5)
        listening.cancel()

    asyncio.run(run())
    assert [e.text for e in s.sink.of(Partial)][-1] == "alpha"
    assert s.sink.of(Dictation) == []
    assert s.states() == [MiloState.LISTENING, MiloState.IDLE]


def test_levels_flow_only_once_shown():
    class LevelMic(GrowingMic):
        def start(self, on_level) -> None:
            self.active = True
            self.on_level = on_level

    s, mic = Stack(), LevelMic()
    mic.active = False
    listening = Listening(mic, HearingStt(), InlineExecutor(), s.ui, s.dictation, s.live_talk, s.context)
    counts = []

    async def run():
        listening.start(ListenMode.DICTATE, tentative=True)
        mic.on_level(0.5)
        await settle()
        counts.append(len(s.sink.of(Level)))
        listening.confirm()
        mic.on_level(0.6)
        await settle()
        counts.append(len(s.sink.of(Level)))

    asyncio.run(run())
    assert counts == [0, 1]
    assert s.sink.of(Level) == [Level(0.6)]
