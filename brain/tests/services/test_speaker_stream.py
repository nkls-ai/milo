"""The Speaker with a streaming voice: one delivery per reply, sentence by sentence, with hold, barge-in and a
fallback that takes over when the stream breaks."""

import asyncio

import numpy as np

from milo.core.types import Emotion, MiloState
from milo.services.fallback_voice import NOTICE, RETRY_S, FallbackVoice, VoiceNotice
from milo.services.speech_audio import END_PAD_S, PauseLimiter, SILENCE_DB
from tests.fakes import FakeAudioOutput, FakeStreamingVoice, FakeVoice
from tests.services.stack import Stack, settle


def samples(seconds: float) -> int:
    return int(round(seconds * FakeVoice.sample_rate))


def test_a_reply_goes_to_one_stream_sentence_by_sentence_without_added_pauses():
    voice = FakeStreamingVoice()
    s = Stack(voice=voice)

    async def run():
        assert await s.speaker.say("Klar, mach ich. Morgen um zehn hast du das Meeting.", Emotion.HAPPY)
        await settle()

    asyncio.run(run())
    assert len(voice.streams) == 1 and voice.streams[0].finished
    assert voice.streams[0].sent == ["Klar, mach ich.", "Morgen um zehn hast du das Meeting."], \
        "whole sentences: clauses on their own break the voice's prosody"
    assert voice.spoken == [], "nothing synthesized piece by piece"
    first, second = (10 * len(t) for t in voice.streams[0].sent)
    assert sum(s.output.fed[:-1]) == first + second, \
        "the voice's audio as it came, with its own pauses: none added between pieces"
    assert s.output.fed[-1] == samples(END_PAD_S)
    assert len(s.output.streams) == 1
    assert s.bubbles() == ["Klar, mach ich.", "Klar, mach ich. Morgen um zehn hast du das Meeting."]
    assert s.states() == [MiloState.SPEAKING, MiloState.IDLE]


def test_each_sentence_goes_out_the_moment_it_is_written_before_any_audio():
    voice = FakeStreamingVoice(auto=False)
    s = Stack(voice=voice, output=FakeAudioOutput(block=True))

    async def run():
        u = s.speaker.utterance(Emotion.NEUTRAL)
        u.add("Sure. ")
        await settle()
        stream = voice.streams[0]
        assert stream.sent == [], "a sentence counts once the next word starts (no split at 2.5)"
        u.add("It is nine. Then")
        await settle()
        assert stream.sent == ["Sure. It is nine."], "every whole sentence so far, in one piece"
        assert u.ready_in() > 0 and s.output.fed == []
        u.add(" lunch")
        finishing = asyncio.create_task(u.finish())
        await settle()
        assert stream.sent == ["Sure. It is nine.", "Then lunch"] and stream.finished
        stream.play(0)
        stream.play(1)
        stream.end()
        await settle()
        assert s.bubbles()[-1] == "Sure. It is nine. Then lunch"
        s.output.block = False
        s.output.interrupt()
        await finishing

    asyncio.run(run())


def test_barge_in_cancels_the_stream_and_cuts_the_audio():
    voice = FakeStreamingVoice(auto=False)
    s = Stack(voice=voice, output=FakeAudioOutput(block=True))

    async def run():
        u = s.speaker.utterance(Emotion.NEUTRAL)
        u.add("One two three. Four ")
        await settle()
        voice.streams[0].play(0)
        await settle()
        s.speaker.interrupt()
        assert await u.finish() is False

    asyncio.run(run())
    assert voice.streams[0].cancelled and s.output.interrupts == 1
    assert s.bubbles() == ["One two three."]


def test_hold_and_resume_go_on_in_a_fresh_stream_from_the_sentence_that_was_cut():
    voice = FakeStreamingVoice(auto=False)
    s = Stack(voice=voice, output=FakeAudioOutput(block=True))

    async def run():
        u = s.speaker.utterance(Emotion.NEUTRAL)
        u.add("One two three. Four five six. Seven")
        await settle()
        first = voice.streams[0]
        first.play(0)
        await settle()
        s.speaker.hold()
        await settle()
        assert first.cancelled and u.held
        u.add(" eight.")
        finishing = asyncio.create_task(u.finish())
        await settle()
        assert len(voice.streams) == 1, "nothing goes out while held"
        s.output.block = False
        assert s.speaker.resume()
        await settle()
        second = voice.streams[1]
        assert second.sent == ["One two three. Four five six.", "Seven eight."]
        second.play(0)
        second.play(1)
        second.end()
        assert await finishing is True

    asyncio.run(run())


def test_a_stream_that_breaks_goes_on_piece_by_piece_with_the_local_voice_and_milo_says_so_once():
    cloud, local = FakeStreamingVoice(auto=False), FakeVoice()
    switches = []
    voice = FallbackVoice(cloud, lambda: local, on_switch=switches.append)
    s = Stack(voice=voice)

    async def run():
        u = s.speaker.utterance(Emotion.NEUTRAL)
        u.add("One two three. Four")
        await settle()
        stream = cloud.streams[0]
        stream.play(0)
        u.add(" five six. Seven eight.")
        finishing = asyncio.create_task(u.finish())
        await settle()
        assert stream.sent == ["One two three.", "Four five six.", "Seven eight."]
        stream.fail("ElevenLabs unreachable")
        assert await finishing is True
        assert s.speaker.voice.stream() is None, "the next reply uses the local voice right away"

    asyncio.run(run())
    assert local.spoken == ["Four five six. Seven eight."], "what wasn't heard, in the local voice"
    assert s.output.streams[0]["sample_rate"] == FakeStreamingVoice.sample_rate and len(s.output.streams) == 1
    assert switches == ["ElevenLabs unreachable"]
    assert s.bubbles()[-1] == "One two three. Four five six. Seven eight."


def test_the_cloud_voice_gets_another_try_after_a_while():
    now = [0.0]
    cloud, local = FakeStreamingVoice(), FakeVoice()
    switches = []
    voice = FallbackVoice(cloud, lambda: local, on_switch=switches.append, clock=lambda: now[0])
    voice.warm()
    assert not local.warmed, "the local voice loads only when it is needed: it holds gigabytes"

    async def run():
        assert voice.stream() is not None
        voice.failed("offline")
        assert voice.stream() is None
        voice.failed("still offline")
        assert switches == ["offline"], "said once"
        voice.synthesize("Hm.")
        assert local.warmed
        now[0] += RETRY_S + 1
        assert voice.stream() is not None

    asyncio.run(run())


def test_synthesize_falls_back_and_comes_back_at_the_primary_rate():
    class Cloud(FakeStreamingVoice):
        sample_rate = 2000

        def synthesize(self, text):
            from milo.core.types import VoiceUnavailable
            raise VoiceUnavailable("no credits left")

    local = FakeVoice()  # 1000 Hz
    voice = FallbackVoice(Cloud(), lambda: local)
    audio = voice.synthesize("Hm.")
    assert voice.sample_rate == 2000 and len(audio) == 2 * 10 * len("Hm."), "resampled for the open stream"


def test_the_notice_waits_until_milo_is_quiet():
    said = []
    busy = [True]

    async def run():
        notice = VoiceNotice(said.append, busy=lambda: busy[0], wait_s=5)
        notice.loop = asyncio.get_running_loop()
        notice("offline")
        await asyncio.sleep(0.05)
        assert said == []
        busy[0] = False
        await asyncio.sleep(0.5)

    asyncio.run(run())
    assert said == [NOTICE]


def test_the_notice_is_said_once_per_reason():
    """Live (2026-10-31): with the ElevenLabs quota used up, every retry two minutes later failed the same way, and
    Milo said "I can't reach the cloud…" again each time."""
    said = []

    async def run():
        notice = VoiceNotice(said.append, busy=lambda: False, wait_s=5)
        notice.loop = asyncio.get_running_loop()
        for reason in ("ElevenLabs: You have exceeded your quota.", "ElevenLabs: You have exceeded your quota.",
                       "offline"):
            notice(reason)
            await asyncio.sleep(0.05)

    asyncio.run(run())
    assert said == [NOTICE, NOTICE], "the quota once, then being offline, a new reason"


def test_a_streaming_voice_that_cannot_stream_now_speaks_piece_by_piece():
    voice = FakeStreamingVoice(available=False)
    s = Stack(voice=voice)

    async def run():
        assert await s.speaker.say("Hello there, my good old friend. How are you?", Emotion.HAPPY)

    asyncio.run(run())
    assert voice.spoken == ["Hello there, my good old friend.", "How are you?"]


def test_the_talk_key_prepares_the_streaming_voice():
    voice = FakeStreamingVoice()
    s = Stack(voice=voice)

    async def run():
        s.live_talk.prepare()

    asyncio.run(run())
    assert voice.prepared == 1


def test_long_pauses_are_shortened_and_the_lead_trimmed():
    rate = 1000
    tone = np.full(200, 0.3, dtype=np.float32)
    quiet = lambda seconds: np.zeros(int(seconds * rate), dtype=np.float32)  # noqa: E731
    limiter = PauseLimiter(rate, max_pause_s=0.5)
    audio = np.concatenate([quiet(0.2), tone, quiet(1.2), tone, quiet(0.3), tone])
    out = np.concatenate([limiter(audio[:333]), limiter(audio[333:]), limiter.flush()])
    db = 20 * np.log10(np.abs(out) + 1e-9)
    loud = np.flatnonzero(db > SILENCE_DB)
    assert loud[0] == 30, "30 ms kept before the first sound"
    gaps = np.diff(loud)
    assert sorted(gaps[gaps > 1] - 1) == [300, 500], "a 0.3 s pause stays, 1.2 s becomes 0.5 s"
    assert len(out) == len(audio) - 170 - 700
