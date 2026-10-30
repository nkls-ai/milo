"""Talk mode with a cloud transcriber listening along, and the fall back to the local one."""

import asyncio

from milo.core.events import Heard, Partial
from milo.core.types import ListenMode, LiveMode, MiloState
from milo.services.cloud_hearing import RETRY_S, CloudHearing
from milo.services.listening import Listening
from tests.fakes import FakeAudioInput, FakeLiveModel, FakeStreamingTranscriber, FakeTranscriber
from tests.services.stack import Stack, settle


def test_a_talk_recording_streams_while_it_is_made_and_its_text_starts_the_turn():
    cloud = FakeStreamingTranscriber("wie spät ist es")
    s = Stack(model=FakeLiveModel(["[neutral] Neun."]), transcriber=FakeTranscriber("whisper's take"),
              hearing=CloudHearing(cloud), mic=FakeAudioInput(seconds=1.0))

    async def run():
        s.listening.start(ListenMode.TALK)
        await asyncio.sleep(0.15)
        session = cloud.sessions[0]
        assert session.fed and sum(session.fed) == 16000, "the microphone's audio went out while the key was held"
        await s.listening.stop()
        await settle()
        assert session.finished and sum(session.fed) == 16000, "nothing sent twice"

    asyncio.run(run())
    assert s.sink.of(Heard) == [Heard("wie spät ist es")]
    assert s.transcriber.calls == [], "no local pass"


def test_when_the_cloud_fails_the_recording_is_transcribed_locally_and_milo_says_so_once():
    now = [0.0]
    switches = []
    cloud = FakeStreamingTranscriber(fail="ElevenLabs unreachable")
    hearing = CloudHearing(cloud, on_switch=switches.append, clock=lambda: now[0])
    s = Stack(model=FakeLiveModel(["[neutral] Neun."], ["[neutral] Zehn."], ["[neutral] Elf."]),
              transcriber=FakeTranscriber("wie spät ist es", "und jetzt", "und nun"), hearing=hearing)

    async def run():
        for _ in range(2):
            s.listening.start(ListenMode.TALK)
            await s.listening.stop()
            await settle()
        now[0] += RETRY_S + 1
        cloud.fail = ""
        cloud.texts.append("wieder da")
        s.listening.start(ListenMode.TALK)
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert [h.text for h in s.sink.of(Heard)] == ["wie spät ist es", "und jetzt", "wieder da"]
    assert len(cloud.sessions) == 2, "the second recording didn't try the cloud while it was down"
    assert switches == ["ElevenLabs unreachable"]


class _Broken(FakeStreamingTranscriber):
    """A session whose finish() fails with something other than VoiceUnavailable, like a bug in a library."""

    def session(self, on_partial=None):
        session = super().session(on_partial)

        async def finish():
            raise RuntimeError("the websocket library broke")

        session.finish = finish
        return session


def test_an_unexpected_cloud_error_falls_back_to_the_mac_instead_of_leaving_milo_transcribing():
    switches = []
    s = Stack(model=FakeLiveModel(["[neutral] Neun."]), transcriber=FakeTranscriber("wie spät ist es"),
              hearing=CloudHearing(_Broken(), on_switch=switches.append))

    async def run():
        s.listening.start(ListenMode.TALK)
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert [h.text for h in s.sink.of(Heard)] == ["wie spät ist es"], "transcribed here instead"
    assert s.ui.state is not MiloState.TRANSCRIBING
    assert switches, "and the cloud rests for a while"


def test_dictation_stays_on_the_mac_unless_allowed():
    cloud = FakeStreamingTranscriber("cloud text")
    s = Stack(transcriber=FakeTranscriber("local text"), hearing=CloudHearing(cloud))

    async def run():
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()
        s.listening._hearing.dictation = True
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()

    asyncio.run(run())
    assert len(cloud.sessions) == 1 and len(s.transcriber.calls) == 1
    assert [text for text, _ in s.history.entries] == ["LOCAL TEXT", "CLOUD TEXT"]


def test_typed_dictation_never_goes_to_the_cloud():
    cloud = FakeStreamingTranscriber("cloud text")
    s = Stack(transcriber=FakeTranscriber("local"), hearing=CloudHearing(cloud, dictation=True))
    s.listening = Listening(s.mic, s.transcriber, s.listening._executor, s.ui, s.dictation, s.live_talk, s.context,
                            LiveMode.TYPE, hearing=s.listening._hearing)

    async def run():
        s.listening.start(ListenMode.DICTATE)
        await s.listening.stop()

    asyncio.run(run())
    assert cloud.sessions == []


def test_a_cancelled_recording_cancels_its_session():
    cloud = FakeStreamingTranscriber("never")
    s = Stack(hearing=CloudHearing(cloud))

    async def run():
        s.listening.start(ListenMode.TALK)
        await settle()
        s.listening.cancel()
        await settle()

    asyncio.run(run())
    assert cloud.sessions[0].cancelled and not cloud.sessions[0].finished


def test_with_live_words_on_the_cloud_text_still_wins_and_no_final_local_pass_runs():
    cloud = FakeStreamingTranscriber("die Wolke")
    s = Stack(model=FakeLiveModel(["[neutral] Ja."]), transcriber=FakeTranscriber("lokal"), hearing=CloudHearing(cloud))
    s.listening.live_mode = LiveMode.PREVIEW

    async def run():
        s.listening.start(ListenMode.TALK)
        await settle()
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert [h.text for h in s.sink.of(Heard)] == ["die Wolke"]
    assert s.transcriber.calls == []


def test_the_cloud_s_guesses_are_the_live_words_and_the_local_model_stays_asleep():
    cloud = FakeStreamingTranscriber("die Wolke hört zu")
    s = Stack(model=FakeLiveModel(["[neutral] Ja."]), transcriber=FakeTranscriber("lokal"), hearing=CloudHearing(cloud),
              mic=FakeAudioInput(seconds=2.0))
    s.listening.live_mode = LiveMode.PREVIEW

    async def run():
        s.listening.start(ListenMode.TALK)
        await asyncio.sleep(0.3)
        cloud.sessions[0].on_partial("die Wolke")
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert s.sink.of(Partial) == [Partial("die Wolke")]
    assert [h.text for h in s.sink.of(Heard)] == ["die Wolke hört zu"]
    assert s.transcriber.calls == [] and s.transcriber.previews == [], "no live passes on the Mac"
    assert s.transcriber.wakes == 0, "the local model wasn't paged in for nothing"


def test_while_the_cloud_rests_the_local_model_is_woken_and_shows_the_live_words():
    now = [0.0]
    cloud = FakeStreamingTranscriber(fail="offline")
    s = Stack(model=FakeLiveModel(["[neutral] Ja."], ["[neutral] Nein."]),
              transcriber=FakeTranscriber("eins", "zwei"), hearing=CloudHearing(cloud, clock=lambda: now[0]))

    async def run():
        s.listening.start(ListenMode.TALK)
        await s.listening.stop()
        await settle()
        assert s.transcriber.wakes == 0
        s.listening.start(ListenMode.TALK)
        await settle()
        assert s.transcriber.wakes == 1, "this recording is transcribed here"
        await s.listening.stop()
        await settle()

    asyncio.run(run())
    assert [h.text for h in s.sink.of(Heard)] == ["eins", "zwei"]
    assert len(cloud.sessions) == 1
