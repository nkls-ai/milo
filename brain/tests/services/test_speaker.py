import asyncio

from milo.core.events import Bubble, EmotionChanged, Level, StateChanged
from milo.core.types import Emotion, MiloState
from milo.services.levels import throttled_levels
from milo.services.speaker import SECONDS_PER_CHAR_WITHOUT_AUDIO
from tests.fakes import FakeAudioOutput, FakeVoice, RecordingSink
from tests.services.stack import Stack, settle


def test_say_speaks_chunk_by_chunk_on_one_stream_with_a_growing_bubble():
    s = Stack()

    async def run():
        assert await s.speaker.say("Hello there, my good old friend. How are you?", Emotion.HAPPY)
        await settle()

    asyncio.run(run())
    assert s.voice.spoken == ["Hello there, my good old friend.", "How are you?"]
    assert len(s.output.streams) == 1, "one stream per utterance, so chunks play without gaps"
    assert s.output.streams[0]["sample_rate"] == FakeVoice.sample_rate
    assert s.output.fed == [10 * len("Hello there, my good old friend."), 10 * len("How are you?")]
    assert s.bubbles() == ["Hello there, my good old friend.", "Hello there, my good old friend. How are you?"]
    assert s.states() == [MiloState.SPEAKING, MiloState.IDLE]
    assert s.sink.of(EmotionChanged) == [EmotionChanged(Emotion.HAPPY)]
    assert s.sink.of(Level), "voice loudness reaches the app"
    assert not s.ui.speaking and not s.speaker.active


def test_with_the_voice_off_the_bubble_still_grows_at_speaking_pace_in_silence():
    s = Stack()
    s.speaker.silent = True

    async def run():
        assert await s.speaker.say("Hello there, my good old friend. How are you?", Emotion.HAPPY)
        await settle()

    asyncio.run(run())
    assert s.voice.spoken == []
    assert s.bubbles() == ["Hello there, my good old friend.", "Hello there, my good old friend. How are you?"]
    assert s.states() == [MiloState.SPEAKING, MiloState.IDLE]
    rate = FakeVoice.sample_rate * SECONDS_PER_CHAR_WITHOUT_AUDIO
    assert s.output.fed == [int(rate * len("Hello there, my good old friend.")), int(rate * len("How are you?"))]


def test_an_utterance_speaks_text_as_it_arrives():
    s = Stack(output=FakeAudioOutput(block=True))

    async def run():
        utterance = s.speaker.utterance(Emotion.EXCITED)
        utterance.add("Oh wow, ")
        await settle()
        assert s.voice.spoken == [], "two words: too short for a first chunk"
        utterance.add("that is great, ")
        await settle()
        assert s.voice.spoken == ["Oh wow, that is great,"]
        assert s.ui.state is MiloState.SPEAKING and s.bubbles() == ["Oh wow, that is great,"]
        utterance.add("really")
        finishing = asyncio.create_task(utterance.finish())
        await settle()
        assert s.voice.spoken[-1] == "really" and not finishing.done(), "waits for the audio to play"
        s.output.block = False
        s.output.interrupt()  # the fake's way to let drain() return
        await finishing

    asyncio.run(run())
    assert len(s.output.streams) == 1 and len(s.output.fed) == 2


def test_interrupt_stops_speech_and_drops_the_rest():
    s = Stack(output=FakeAudioOutput(block=True))

    async def run():
        utterance = s.speaker.utterance(Emotion.NEUTRAL)
        utterance.add("One two three four five, ")
        await settle()
        assert s.speaker.active and s.ui.state is MiloState.SPEAKING
        s.speaker.interrupt()
        utterance.add("four five six, seven. ")
        assert await utterance.finish() is False
        await settle()

    asyncio.run(run())
    assert s.voice.spoken == ["One two three four five,"]
    assert s.output.interrupts == 1
    assert s.bubbles() == ["One two three four five,"]
    assert s.states() == [MiloState.SPEAKING, MiloState.IDLE]
    assert not s.speaker.active and not s.ui.speaking


def test_interrupt_before_any_audio_never_opens_the_stream_twice():
    s = Stack()

    async def run():
        utterance = s.speaker.utterance(Emotion.NEUTRAL)
        s.speaker.interrupt()
        utterance.add("Never said, at all.")
        await utterance.finish()

    asyncio.run(run())
    assert s.output.streams == [] and s.voice.spoken == []


def test_tts_failure_still_shows_the_text_and_plays_silence_for_its_length():
    s = Stack(voice=FakeVoice(fail=True))

    async def run():
        await s.speaker.say("Hi there, how are you. Yo.", Emotion.HAPPY)

    asyncio.run(run())
    assert s.bubbles() == ["Hi there, how are you.", "Hi there, how are you. Yo."]
    silence = lambda text: int(SECONDS_PER_CHAR_WITHOUT_AUDIO * len(text) * FakeVoice.sample_rate)
    assert s.output.fed == [silence("Hi there, how are you."), silence("Yo.")]
    assert s.states() == [MiloState.SPEAKING, MiloState.IDLE]


def test_silent_speech_shows_bubble_and_emotion_without_state_change():
    s = Stack()

    async def run():
        await s.speaker.say("Psst. Quiet now.", Emotion.SLEEPY, speak=False)

    asyncio.run(run())
    assert s.sink.events == [EmotionChanged(Emotion.SLEEPY), Bubble("Psst. Quiet now.")]
    assert s.voice.spoken == [] and s.output.streams == []


def test_new_speech_replaces_running_speech():
    s = Stack(output=FakeAudioOutput(block=True))

    async def run():
        first = s.speaker.say("First answer here.", Emotion.NEUTRAL)
        await settle()
        s.output.block = False
        second = s.speaker.say("Second.", Emotion.HAPPY)
        results = await asyncio.gather(first, second)
        await settle()
        return results

    assert asyncio.run(run()) == [False, True]
    assert s.bubbles() == ["First answer here.", "Second."]
    assert len(s.output.streams) == 2
    assert s.states() == [MiloState.SPEAKING, MiloState.SPEAKING, MiloState.IDLE]
    assert not s.ui.speaking


def test_levels_are_throttled_but_silence_always_passes():
    sink = RecordingSink()
    now = [0.0]

    async def run():
        on_level = throttled_levels(sink, asyncio.get_running_loop(), monotonic=lambda: now[0])
        on_level(0.5)
        now[0] = 0.01
        on_level(0.6)  # within 50 ms: dropped
        on_level(0.0)  # silence: kept
        now[0] = 0.07
        on_level(0.12345)
        await settle()

    asyncio.run(run())
    assert sink.of(Level) == [Level(0.5), Level(0.0), Level(0.123)]


def test_levels_from_another_thread_reach_the_sink_on_the_loop():
    sink = RecordingSink()

    async def run():
        import threading
        on_level = throttled_levels(sink, asyncio.get_running_loop())
        t = threading.Thread(target=on_level, args=(0.4,))
        t.start()
        t.join()
        await settle()

    asyncio.run(run())
    assert sink.of(Level) == [Level(0.4)]
    assert all(not isinstance(e, StateChanged) for e in sink.events)


def test_pace_fits_overhead_and_per_char_cost_from_pieces_of_different_length():
    from milo.services.speaker import SynthesisPace

    pace = SynthesisPace()
    for chars in (40, 80, 120, 160):
        pace.learn(chars, 1.5 + 0.02 * chars)
    assert abs(pace.overhead_s - 1.5) < 1e-6 and abs(pace.seconds_per_char - 0.02) < 1e-6
    assert pace.budget(4.0) == int((4.0 * pace.margin - 1.5) / 0.02)
    assert pace.budget(0.5) == 0



def test_interrupt_cancels_the_synthesis_in_flight():
    s = Stack(output=FakeAudioOutput(block=True))

    async def run():
        utterance = s.speaker.utterance(Emotion.NEUTRAL)
        utterance.add("One two three four five, ")
        await settle()
        s.speaker.interrupt()
        assert await utterance.finish() is False

    asyncio.run(run())
    assert s.voice.cancels == 1, "frees the TTS thread so the next reply needn't wait for this one"
