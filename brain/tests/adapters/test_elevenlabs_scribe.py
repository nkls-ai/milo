"""Scribe realtime against a fake ElevenLabs: a WAV file plays as the microphone in real time, its audio streams
out while "recording", and the commit on release brings back the text."""

import asyncio
import base64
import json
from urllib.parse import parse_qs, parse_qsl, urlsplit

import numpy as np
import pytest
from websockets.asyncio.server import serve

from milo.adapters.audio.wav_file import WavMicrophone, write_wav
from milo.adapters.stt import elevenlabs_scribe
from milo.adapters.stt.elevenlabs_scribe import MAX_KEYTERMS, ScribeRealtime
from milo.core.types import STT_SAMPLE_RATE, VoiceUnavailable
from milo.services.cloud_hearing import CloudHearing

KEY = "sk_" + "s" * 48


class FakeScribe:
    """Collects the audio; answers the commit with how many samples it heard, or with `reply` if set."""

    def __init__(self, reply: dict | None = None, silent: bool = False, partial: str = ""):
        self.reply = reply
        self.partial = partial
        self.silent = silent
        self.audio = b""
        self.chunks: list[int] = []
        self.query: dict = {}
        self.keys: list[str] = []
        self.committed_after: list[int] = []

    async def handler(self, ws):
        self.query = parse_qs(urlsplit(ws.request.path).query)
        self.keys.append(ws.request.headers.get("xi-api-key"))
        await ws.send(json.dumps({"message_type": "session_started", "session_id": "x", "config": {}}))
        async for raw in ws:
            m = json.loads(raw)
            assert m["message_type"] == "input_audio_chunk" and m["sample_rate"] == STT_SAMPLE_RATE
            pcm = base64.b64decode(m["audio_base_64"])
            if pcm:
                self.audio += pcm
                self.chunks.append(len(pcm))
                if self.partial:
                    await ws.send(json.dumps({"message_type": "partial_transcript", "text": self.partial}))
            if m["commit"]:
                self.committed_after.append(len(self.audio))
                if self.silent:
                    continue
                await ws.send(json.dumps(self.reply or {"message_type": "committed_transcript",
                                                        "text": f"heard {len(self.audio) // 2} samples"}))


async def started(fake):
    server = await serve(fake.handler, "127.0.0.1", 0)
    return server, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


def engine(url, tmp_path, **kw) -> ScribeRealtime:
    key = tmp_path / "key"
    key.write_text(KEY, encoding="utf-8")
    return ScribeRealtime(key, server=url, **kw)


def test_a_recording_streams_while_it_plays_and_the_commit_brings_the_text(tmp_path):
    t = np.arange(int(1.2 * STT_SAMPLE_RATE)) / STT_SAMPLE_RATE
    clip = (0.3 * np.sin(2 * np.pi * 220 * t) * np.sin(np.pi * t / 1.2)).astype(np.float32)
    write_wav(tmp_path / "said.wav", clip, STT_SAMPLE_RATE)
    fake = FakeScribe()

    async def run():
        server, url = await started(fake)
        async with server:
            mic = WavMicrophone(tmp_path / "said.wav")
            hearing = CloudHearing(engine(url, tmp_path, keyterms=("Milo",)))
            mic.start(lambda level: None)
            recording = hearing.start(mic)
            await asyncio.sleep(0.7)
            streamed_before_release = len(fake.audio)
            await asyncio.sleep(0.6)
            audio = mic.stop()
            text = await hearing.transcribe(recording, audio)
            return streamed_before_release, audio, text

    before, audio, text = asyncio.run(run())
    assert before > 0.3 * STT_SAMPLE_RATE * 2, "audio went out while the user was still speaking"
    sent = np.frombuffer(fake.audio, "<i2")
    assert len(sent) == len(audio) and np.allclose(sent / 32767, np.clip(audio, -1, 1), atol=1e-4), \
        "every sample once, in order"
    assert text == f"heard {len(audio)} samples"
    assert fake.committed_after == [len(fake.audio)], "one commit, after all the audio"
    assert max(fake.chunks) <= STT_SAMPLE_RATE * 2, "at most a second per message"
    assert fake.query["model_id"] == ["scribe_v2_realtime"] and fake.query["commit_strategy"] == ["manual"]
    assert fake.query["secondary_languages"] == ["de", "en"] and fake.query["keyterms"] == ["Milo"]
    assert fake.keys == [KEY]


def test_errors_and_silence_from_the_service(tmp_path, monkeypatch):
    monkeypatch.setattr(elevenlabs_scribe, "FINAL_TIMEOUT_S", 0.3)

    async def attempt(fake):
        server, url = await started(fake)
        async with server:
            session = engine(url, tmp_path).session()
            session.feed(np.zeros(1600, np.float32))
            return await session.finish()

    assert asyncio.run(attempt(FakeScribe({"message_type": "committed_transcript", "text": ""}))) == ""
    with pytest.raises(VoiceUnavailable, match="quota"):
        asyncio.run(attempt(FakeScribe({"message_type": "quota_exceeded", "error": "quota exceeded"})))
    with pytest.raises(VoiceUnavailable, match="no text"):
        asyncio.run(attempt(FakeScribe(silent=True)))


def test_nobody_listening_or_no_key_is_voice_unavailable(tmp_path):
    async def run(scribe):
        session = scribe.session()
        session.feed(np.zeros(1600, np.float32))
        return await session.finish()

    with pytest.raises(VoiceUnavailable, match="unreachable|refused|closed|no text"):
        asyncio.run(run(engine("ws://127.0.0.1:9", tmp_path)))
    with pytest.raises(VoiceUnavailable, match="no ElevenLabs key"):
        asyncio.run(run(ScribeRealtime(tmp_path / "missing")))


def test_partial_transcripts_are_the_live_words_until_the_commit(tmp_path):
    fake = FakeScribe(partial="hallo Mi")
    partials: list[str] = []

    async def run():
        server, url = await started(fake)
        async with server:
            session = engine(url, tmp_path).session(partials.append)
            session.feed(np.zeros(STT_SAMPLE_RATE // 4, dtype=np.float32))
            for _ in range(50):
                if partials:
                    break
                await asyncio.sleep(0.02)
            return await session.finish()

    assert asyncio.run(run()) == f"heard {STT_SAMPLE_RATE // 4} samples"
    assert partials and set(partials) == {"hallo Mi"}


def test_learned_words_join_the_keyterms_up_to_a_cap(tmp_path):
    scribe = engine("ws://127.0.0.1:1", tmp_path, keyterms=("Milo",))
    scribe.use_vocabulary(["Claude Code", "Milo", "x" * 51, *(f"Name{i}" for i in range(100))])
    assert scribe.keyterms[:3] == ("Milo", "Claude Code", "Name0")
    assert len(scribe.keyterms) == MAX_KEYTERMS
    assert ("keyterms", "Claude Code") in parse_qsl(urlsplit(scribe._url()).query)
    scribe.use_vocabulary([])
    assert scribe.keyterms == ("Milo",)


def test_milo_is_a_keyterm_unless_the_config_says_otherwise():
    """"Hey, Milo" was heard as "Hey, Manuel": his own name is always worth the keyterm."""
    from milo.adapters.stt.elevenlabs_scribe import ScribeOptions

    assert ScribeOptions().keyterms == ("Milo",)


def test_the_committed_text_says_which_language_it_was(tmp_path):
    # Milo answers in the language of the message (ADR 0028): the session asks Scribe to detect it.
    async def attempt(fake):
        server, url = await started(fake)
        async with server:
            session = engine(url, tmp_path).session()
            session.feed(np.zeros(1600, np.float32))
            text = await session.finish()
            return text, session.language, fake.query

    stamped = {"message_type": "committed_transcript_with_timestamps", "text": "open YouTube", "language_code": "eng",
               "words": []}
    text, language, query = asyncio.run(attempt(FakeScribe(stamped)))
    assert (text, language) == ("open YouTube", "eng"), "the stamped message alone is enough"
    assert query["include_language_detection"] == ["true"]
    text, language, _ = asyncio.run(attempt(FakeScribe()))
    assert text.startswith("heard") and language == "", "no language said: the brain guesses from the words"


def test_the_batch_transcriber_sends_a_whole_recording_and_waits_longer_for_a_longer_one(tmp_path):
    # ADR 0027: `[stt] use = "elevenlabs"` is how a computer without a local Whisper hears.
    from milo.adapters.stt.elevenlabs_scribe import ScribeTranscriber
    from milo.core.ports import Transcriber

    fake = FakeScribe()

    async def serve_for(seconds: float):
        server, url = await started(fake)
        async with server:
            batch = ScribeTranscriber(engine(url, tmp_path))
            audio = np.zeros(int(seconds * STT_SAMPLE_RATE), dtype=np.float32)
            return batch, await asyncio.to_thread(batch.transcribe, audio)

    batch, text = asyncio.run(serve_for(2.5))
    assert isinstance(batch, Transcriber)
    assert text == f"heard {int(2.5 * STT_SAMPLE_RATE)} samples" and fake.committed_after == [len(fake.audio)]
    assert batch.preview(np.zeros(100, dtype=np.float32)) == "", "no live words: that would be a session a pass"


def test_the_batch_transcriber_stops_on_interrupt_and_says_when_the_service_is_gone(tmp_path):
    from milo.adapters.stt.elevenlabs_scribe import ScribeTranscriber
    from milo.core.types import Interrupted

    fake = FakeScribe(silent=True)

    async def run():
        server, url = await started(fake)
        async with server:
            batch = ScribeTranscriber(engine(url, tmp_path))
            pass_ = asyncio.create_task(asyncio.to_thread(batch.transcribe, np.zeros(1600, dtype=np.float32)))
            await asyncio.sleep(0.3)
            batch.interrupt()
            with pytest.raises(Interrupted):
                await pass_

    asyncio.run(run())
    gone = ScribeTranscriber(engine("ws://127.0.0.1:9", tmp_path))
    with pytest.raises(VoiceUnavailable):
        gone.transcribe(np.zeros(1600, dtype=np.float32))
