import asyncio

from milo.core.events import Bubble, Dictation, EmotionChanged, Heard, Level, StateChanged, Status
from milo.core.types import Emotion, HarnessError, ListenMode, MiloState
from milo.services.live_talk import HICCUP
from tests.fakes import FakeAudioInput, FakeAudioOutput, FakeLiveModel, FakeTranscriber
from tests.services.stack import Stack, settle


class BrokenTranscriber(FakeTranscriber):
    def transcribe(self, audio):
        raise RuntimeError("mlx died")


def test_talk_turn_end_to_end():
    s = Stack(model=FakeLiveModel(["[excited] Sure thing, ", "it is nine. ", "Bye now."]),
              transcriber=FakeTranscriber("what time is it"))

    async def run():
        s.listening.start(ListenMode.TALK)
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    flow = [e for e in s.sink.events if not isinstance(e, Level)]
    assert flow == [
        StateChanged(MiloState.LISTENING),
        StateChanged(MiloState.TRANSCRIBING),
        Heard("what time is it"),
        StateChanged(MiloState.THINKING),
        EmotionChanged(Emotion.THINKING),
        EmotionChanged(Emotion.EXCITED),
        StateChanged(MiloState.SPEAKING),
        Bubble("Sure thing, it is nine."),
        Bubble("Sure thing, it is nine. Bye now."),
        StateChanged(MiloState.IDLE),
    ]
    assert s.model.turns[0].endswith("\nwhat time is it")
    assert s.voice.spoken == ["Sure thing, it is nine.", "Bye now."]
    assert s.sink.of(Level), "mic loudness reaches the app"


def test_talking_interrupts_speech_barge_in():
    s = Stack(output=FakeAudioOutput(block=True), transcriber=FakeTranscriber(""))

    async def run():
        speech = s.speaker.say("A long story, with many parts. And more.", Emotion.HAPPY)
        await settle()
        s.listening.start(ListenMode.TALK)
        await asyncio.gather(speech, return_exceptions=True)
        await settle()
        assert s.ui.state is MiloState.LISTENING
        await s.listening.stop()

    asyncio.run(run())
    assert s.output.interrupts == 1
    assert s.speaker.current.done and not s.speaker.active
    assert s.states() == [MiloState.SPEAKING, MiloState.LISTENING, MiloState.TRANSCRIBING, MiloState.IDLE]


def test_talking_while_milo_answers_stops_the_model_and_the_audio_then_listens():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] Let me tell you everything, ", "and then some."], ["[happy] Ok."],
                                  gate=gate),
              output=FakeAudioOutput(block=True), transcriber=FakeTranscriber("stop, what about lunch"))

    async def run():
        turn = s.live_talk.start("tell me everything")
        await settle()
        assert s.ui.state is MiloState.SPEAKING
        s.listening.start(ListenMode.TALK)
        assert s.ui.state is MiloState.LISTENING and not s.ui.speaking
        await asyncio.gather(turn, return_exceptions=True)
        assert s.model.interrupts == 1 and s.output.interrupts == 1
        s.output.block = False
        gate.set()
        await s.listening.stop()
        await settle()
        await s.live_talk._turn

    asyncio.run(run())
    assert s.model.turns[1].endswith("\nstop, what about lunch")
    assert s.voice.spoken == ["Let me tell you everything,", "Ok."]
    assert s.states() == [MiloState.THINKING, MiloState.SPEAKING, MiloState.LISTENING, MiloState.TRANSCRIBING,
                          MiloState.THINKING, MiloState.SPEAKING, MiloState.IDLE]


def test_talking_while_milo_thinks_cancels_the_turn():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[thinking", "] hm."], gate=gate))

    async def run():
        turn = s.live_talk.start("hard question")
        await settle()
        assert s.ui.state is MiloState.THINKING
        s.listening.start(ListenMode.TALK)
        await asyncio.gather(turn, return_exceptions=True)
        await settle()

    asyncio.run(run())
    assert s.model.interrupts == 1 and s.voice.spoken == []
    assert s.ui.state is MiloState.LISTENING and not s.ui.thinking


def test_dictation_does_not_interrupt_speech_and_rests_in_speaking():
    s = Stack(output=FakeAudioOutput(block=True), transcriber=FakeTranscriber("note"))

    async def run():
        s.speaker.say("Talking right now.", Emotion.HAPPY)
        await settle()
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()
        assert s.speaker.active
        s.speaker.interrupt()
        await settle()

    asyncio.run(run())
    assert s.states() == [MiloState.SPEAKING, MiloState.DICTATING, MiloState.TRANSCRIBING, MiloState.SPEAKING,
                          MiloState.IDLE]


def test_dictation_works_while_a_live_turn_is_thinking():
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy", "] Done."], gate=gate), transcriber=FakeTranscriber("hello world"))
    s.context.update("Notes", 0)

    async def run():
        turn = s.live_talk.start("think hard")
        await settle()
        assert s.live_talk.busy and s.ui.state is MiloState.THINKING
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()
        assert s.live_talk.busy
        assert s.ui.state is MiloState.THINKING, "back to thinking, the turn is still running"
        gate.set()
        await turn
        await settle()

    asyncio.run(run())
    assert s.sink.of(Dictation) == [Dictation("HELLO WORLD")]
    assert s.history.entries == [("HELLO WORLD", "Notes")]
    assert s.states() == [MiloState.THINKING, MiloState.DICTATING, MiloState.TRANSCRIBING, MiloState.THINKING,
                          MiloState.SPEAKING, MiloState.IDLE]


def test_empty_dictation_emits_nothing():
    s = Stack(transcriber=FakeTranscriber("   "))

    async def run():
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()

    asyncio.run(run())
    assert s.sink.of(Dictation) == [] and s.history.entries == []
    assert s.states()[-1] is MiloState.IDLE


def test_silent_talk_turn_goes_back_to_idle_without_calling_the_model():
    s = Stack(transcriber=FakeTranscriber(""))

    async def run():
        s.listening.start(ListenMode.TALK)
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert s.model.turns == []
    assert s.states() == [MiloState.LISTENING, MiloState.TRANSCRIBING, MiloState.IDLE]


def test_model_failure_shows_confused_and_a_bubble():
    s = Stack(model=FakeLiveModel(HarnessError("claude not found", transient=False)))

    async def run():
        await s.live_talk.start("hi")
        await settle()

    asyncio.run(run())
    assert s.sink.of(EmotionChanged)[-1] == EmotionChanged(Emotion.CONFUSED)
    assert s.bubbles() == [HICCUP]
    assert s.states() == [MiloState.THINKING, MiloState.IDLE]
    assert not s.live_talk.busy and not s.ui.thinking


def test_mic_failure_on_barge_in_still_stops_milo_and_rests():
    s = Stack(mic=FakeAudioInput(fail=True), output=FakeAudioOutput(block=True))

    async def run():
        s.speaker.say("Talking a lot here, on and on.", Emotion.HAPPY)
        await settle()
        s.listening.start(ListenMode.TALK)
        await settle()

    asyncio.run(run())
    assert s.output.interrupts == 1
    assert s.sink.of(Status) == [Status("Mic unavailable: no input device")]
    assert s.ui.state is MiloState.IDLE


def test_mic_failure_becomes_a_status():
    s = Stack(mic=FakeAudioInput(fail=True))

    async def run():
        s.listening.start(ListenMode.TALK)
        await s.listening.stop()

    asyncio.run(run())
    assert s.sink.of(Status) == [Status("Mic unavailable: no input device")]
    assert s.states() == []


def test_transcription_failure_becomes_a_status():
    s = Stack(transcriber=BrokenTranscriber())

    async def run():
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()

    asyncio.run(run())
    assert s.sink.of(Status) == [Status("I couldn't transcribe that.")]
    assert s.states() == [MiloState.DICTATING, MiloState.TRANSCRIBING, MiloState.IDLE]


def test_cancel_drops_the_recording():
    s = Stack(transcriber=FakeTranscriber("never used"))

    async def run():
        s.listening.start(ListenMode.TALK)
        s.listening.cancel()
        await s.listening.stop()

    asyncio.run(run())
    assert not s.mic.active and s.transcriber.calls == []
    assert s.states() == [MiloState.LISTENING, MiloState.IDLE]


def test_second_start_while_recording_is_ignored():
    s = Stack()

    async def run():
        s.listening.start(ListenMode.TALK)
        s.listening.start(ListenMode.DICTATE)

    asyncio.run(run())
    assert s.mic.starts == 1
    assert s.states() == [MiloState.LISTENING]
