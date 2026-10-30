"""Talk mode with a cloud transcriber listening along, and the fall back to the local one."""

import asyncio

from milo.core.events import Heard
from milo.core.types import ListenMode, LiveMode
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
