"""The ElevenLabs voice against a fake ElevenLabs: a local WebSocket server that speaks the multi-context protocol,
and a local HTTP server for whole clips. Each audio sample carries the number of the message it speaks, so a test
can tell exactly which samples went to which piece."""

import asyncio
import base64
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
from websockets.asyncio.server import serve
from websockets.protocol import State

from milo.adapters.tts import elevenlabs
from milo.adapters.tts.elevenlabs import ElevenLabsOptions, ElevenLabsVoice
from milo.core.ports import StreamingVoice, VoiceStream
from milo.core.registry import ConfigError
from milo.core.types import VoiceUnavailable

KEY = "sk_" + "k" * 48
SAMPLES_PER_CHAR = 24  # 1 ms at 24 kHz


class FakeElevenLabs:
    """Answers each text message with audio whose samples all equal the message's number (1, 2, ...).

    merge: answer two text messages of a context with one audio message. silent: never answer.
    """

    def __init__(self, merge: bool = False, silent: bool = False):
        self.merge = merge
        self.silent = silent
        self.received: list[dict] = []
        self.paths: list[str] = []
        self.keys: list[str] = []
        self.sockets = []
        self._pending: dict[str, list[tuple[int, str]]] = {}
        self._messages = 0

    async def handler(self, ws):
        self.sockets.append(ws)
        self.paths.append(ws.request.path)
        self.keys.append(ws.request.headers.get("xi-api-key"))
        async for raw in ws:
            m = json.loads(raw)
            self.received.append(m)
            ctx = m.get("context_id", "")
            if m.get("close_context"):
                await self.speak(ws, ctx)
                await ws.send(json.dumps({"audio": "", "isFinal": True, "contextId": ctx}))
            elif m.get("flush"):
                await self.speak(ws, ctx)
            elif m.get("text", " ") != " " and m.get("text"):
                self._messages += 1
                self._pending.setdefault(ctx, []).append((self._messages, m["text"]))
                if not self.merge or len(self._pending[ctx]) >= 2:
                    await self.speak(ws, ctx)

    async def speak(self, ws, ctx: str) -> None:
        pieces = self._pending.pop(ctx, [])
        if self.silent or not pieces:
            return
        pcm = np.concatenate([np.full(SAMPLES_PER_CHAR * len(text), n, dtype="<i2") for n, text in pieces])
        text = "".join(t for _, t in pieces)
        await ws.send(json.dumps({
            "audio": base64.b64encode(pcm.tobytes()).decode(), "isFinal": None, "contextId": ctx,
            "alignment": {"chars": list(text), "charStartTimesMs": list(range(len(text))),
                          "charDurationsMs": [1] * len(text)}}))

    async def say_late(self, ctx: str, text: str) -> None:
        """Audio for a context the client already closed."""
        self._pending[ctx] = [(99, text)]
        await self.speak(self.sockets[-1], ctx)


async def started(fake: FakeElevenLabs):
    server = await serve(fake.handler, "127.0.0.1", 0)
    return server, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


def voice_for(url: str, tmp_path, **kw) -> ElevenLabsVoice:
    key = tmp_path / "elevenlabs.key"
    key.write_text(KEY + "\n", encoding="utf-8")
    kw.setdefault("model", "eleven_flash_v2_5")
    return ElevenLabsVoice(key, "voice123", server=url, **kw)


async def collect(stream: VoiceStream) -> list[tuple[int, np.ndarray]]:
    return [(piece, audio) async for piece, audio in stream]


def message_numbers(items) -> list[tuple[int, set[int]]]:
    """Per yielded item: its piece and the message numbers its samples carry (empty: the end-of-piece mark)."""
    return [(piece, set(np.round(audio * 32768).astype(int).tolist())) for piece, audio in items]


def test_text_streams_in_and_each_piece_gets_its_own_audio(tmp_path):
    fake = FakeElevenLabs()

    async def run():
        server, url = await started(fake)
        async with server:
            voice = voice_for(url, tmp_path, stability=0.4)
            assert isinstance(voice, StreamingVoice)
            stream = voice.stream()
            stream.send("Klar, mach ich.")
            stream.send("Morgen   um zehn.")
            stream.finish()
            items = await collect(stream)
            again = voice.stream()
            again.send("Noch was.")
            again.finish()
            await collect(again)
            await voice.close()
            return items

    items = asyncio.run(run())
    assert message_numbers(items) == [(0, {1}), (0, set()), (1, {2}), (1, set())]
    assert len(items[0][1]) == SAMPLES_PER_CHAR * len("Klar, mach ich. ")
    assert len(fake.paths) == 1, "one connection for every reply"
    path = fake.paths[0]
    assert path.startswith("/v1/text-to-speech/voice123/multi-stream-input?")
    for part in ("model_id=eleven_flash_v2_5", "output_format=pcm_24000", "auto_mode=true"):
        assert part in path
    assert fake.keys == [KEY], "the key goes in a header, never the URL"
    first = [m for m in fake.received if m.get("context_id") == "milo-1"]
    assert first[0] == {"text": " ", "context_id": "milo-1",
                        "voice_settings": {"stability": 0.4, "similarity_boost": 0.75, "speed": 1.0}}
    assert [m.get("text") for m in first[1:3]] == ["Klar, mach ich. ", "Morgen um zehn. "], \
        "whole pieces, tidied, each ending with a space"
    assert first[3:] == [{"context_id": "milo-1", "flush": True}, {"context_id": "milo-1", "close_context": True}]


def test_one_audio_message_spanning_two_pieces_is_split_where_the_second_begins(tmp_path):
    fake = FakeElevenLabs(merge=True)

    async def run():
        server, url = await started(fake)
        async with server:
            voice = voice_for(url, tmp_path)
            stream = voice.stream()
            stream.send("Sure.")
            stream.send("It is nine.")
            stream.finish()
            items = await collect(stream)
            await voice.close()
            return items

    items = asyncio.run(run())
    assert message_numbers(items) == [(0, {1}), (0, set()), (1, {2}), (1, set())]
    assert [len(a) for _, a in items if len(a)] == [SAMPLES_PER_CHAR * len("Sure. "),
                                                   SAMPLES_PER_CHAR * len("It is nine. ")]


def test_barge_in_closes_the_context_drops_its_late_audio_and_keeps_the_connection(tmp_path):
    fake = FakeElevenLabs(merge=True)  # the first piece alone gets no audio yet

    async def run():
        server, url = await started(fake)
        async with server:
            voice = voice_for(url, tmp_path)
            stream = voice.stream()
            stream.send("Das ist ein langer Satz.")
            await asyncio.sleep(0.1)
            stream.cancel()
            assert await collect(stream) == []
            await asyncio.sleep(0.1)
            await fake.say_late("milo-1", "late ")
            fake.merge = False
            nxt = voice.stream()
            nxt.send("Okay.")
            nxt.finish()
            items = await collect(nxt)
            await voice.close()
            return items

    items = asyncio.run(run())
    assert {"context_id": "milo-1", "close_context": True} in fake.received
    assert message_numbers(items) == [(0, {2}), (0, set())], "nothing of the cut-off reply leaks into the next"
    assert len(fake.paths) == 1


def test_a_dropped_connection_fails_the_reply_and_the_next_one_reconnects(tmp_path):
    fake = FakeElevenLabs(silent=True)

    async def run():
        server, url = await started(fake)
        async with server:
            voice = voice_for(url, tmp_path)
            stream = voice.stream()
            stream.send("Hallo.")
            await asyncio.sleep(0.1)
            await fake.sockets[0].close()
            with pytest.raises(VoiceUnavailable):
                await collect(stream)
            fake.silent = False
            nxt = voice.stream()
            nxt.send("Wieder da.")
            nxt.finish()
            items = await collect(nxt)
            await voice.close()
            return items

    assert message_numbers(asyncio.run(run()))[0][0] == 0
    assert len(fake.paths) == 2


def test_an_error_from_the_server_is_voice_unavailable(tmp_path):
    async def refuse(ws):
        await ws.recv()
        await ws.send(json.dumps({"message": "Invalid API key", "error": "invalid_api_key", "code": 1008}))
        await ws.close(1008, "Invalid API key")

    async def run():
        server = await serve(refuse, "127.0.0.1", 0)
        async with server:
            voice = voice_for(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", tmp_path)
            stream = voice.stream()
            stream.send("Hallo.")
            with pytest.raises(VoiceUnavailable, match="Invalid API key"):
                await collect(stream)
            await voice.close()

    asyncio.run(run())


def test_no_audio_for_a_while_means_the_voice_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(elevenlabs, "NO_AUDIO_S", 0.2)
    fake = FakeElevenLabs(silent=True)

    async def run():
        server, url = await started(fake)
        async with server:
            voice = voice_for(url, tmp_path)
            stream = voice.stream()
            stream.send("Hallo?")
            with pytest.raises(VoiceUnavailable, match="no audio"):
                await collect(stream)
            await asyncio.sleep(0.05)
            await voice.close()

    asyncio.run(run())
    # M7: the server keeps only a few contexts open per connection, so a stalled one is closed there too.
    assert {"context_id": "milo-1", "close_context": True} in fake.received


def test_nobody_listening_is_voice_unavailable(tmp_path):
    async def run():
        voice = voice_for("ws://127.0.0.1:9", tmp_path)
        stream = voice.stream()
        stream.send("Hallo.")
        with pytest.raises(VoiceUnavailable, match="unreachable|refused|no audio"):
            await collect(stream)
        await voice.close()

    asyncio.run(run())


def test_without_a_key_warm_fails_so_milo_falls_back(tmp_path):
    voice = ElevenLabsVoice(tmp_path / "missing.key", "voice123")
    with pytest.raises(VoiceUnavailable, match="no ElevenLabs key"):
        voice.warm()


def test_whole_clips_come_over_http_and_the_key_is_never_logged(tmp_path, caplog):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"], seen["key"] = self.path, self.headers["xi-api-key"]
            seen["body"] = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if seen["body"]["text"] == "broke":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(json.dumps({"detail": {"message": "quota exceeded"}}).encode())
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(np.full(480, 1000, dtype="<i2").tobytes())

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        with caplog.at_level(logging.DEBUG):
            voice = voice_for(f"ws://127.0.0.1:{http.server_address[1]}", tmp_path)
            voice.warm()
            audio = voice.synthesize("Hm.")
            with pytest.raises(VoiceUnavailable, match="401: quota exceeded"):
                voice.synthesize("broke")
    finally:
        http.shutdown()
    assert len(audio) == 480 and abs(audio[0] - 1000 / 32768) < 1e-6
    assert seen["path"] == "/v1/text-to-speech/voice123?output_format=pcm_24000" and seen["key"] == KEY
    assert seen["body"]["model_id"] == "eleven_flash_v2_5"
    assert KEY not in caplog.text


class FakeDialogue:
    """The dialogue socket: no contexts, every flushed input is answered in order with audio whose samples equal
    the input's number, then is_final_audio_for_turn. hold: buffer inputs until release() instead."""

    def __init__(self, hold: bool = False):
        self.hold = hold
        self.received: list[dict] = []
        self.paths: list[str] = []
        self.sockets = []
        self._held: list[tuple] = []
        self._inputs = 0

    async def handler(self, ws):
        self.sockets.append(ws)
        self.paths.append(ws.request.path)
        async for raw in ws:
            m = json.loads(raw)
            self.received.append(m)
            for item in m.get("inputs", ()):
                self._inputs += 1
                self._held.append((ws, self._inputs, item["text"]))
            if m.get("flush") and not self.hold:
                await self.release()
            if m.get("close_socket"):
                await ws.send(json.dumps({"is_final": True}))
                await ws.close()

    async def release(self) -> None:
        held, self._held = self._held, []
        for ws, n, text in held:
            if ws.state is not State.OPEN:
                continue  # the client dropped this socket
            await ws.send(json.dumps({"audio": base64.b64encode(np.full(24, n, dtype="<i2").tobytes()).decode()}))
            pcm = np.full(SAMPLES_PER_CHAR * len(text), n, dtype="<i2")
            await ws.send(json.dumps({
                "audio": base64.b64encode(pcm.tobytes()).decode(),
                "alignment": {"chars": list(text), "char_start_times_ms": [24 + i for i in range(len(text))],
                              "char_durations_ms": [1] * len(text)}}))
            await ws.send(json.dumps({"is_final_audio_for_turn": True}))


def test_v4_speaks_over_the_dialogue_socket_one_turn_per_reply(tmp_path):
    fake = FakeDialogue()

    async def run():
        server = await serve(fake.handler, "127.0.0.1", 0)
        async with server:
            voice = voice_for(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", tmp_path,
                              model="eleven_v4_turbo", stability=0.4)
            stream = voice.stream()
            stream.send("Klar, mach ich.")
            stream.send("Morgen   um zehn.")
            stream.finish()
            items = await collect(stream)
            again = voice.stream()
            again.send("Noch was.")
            again.finish()
            more = await collect(again)
            await voice.close()
            return items, more

    items, more = asyncio.run(run())
    numbers = [(p, n) for p, n in message_numbers(items) if n]
    assert numbers == [(0, {1}), (0, {1}), (1, {2}), (1, {2})], "each piece's lead-in stays with that piece"
    assert message_numbers(more)[-1] == (0, set()), "the second reply ends with its own end-of-piece mark"
    assert len(fake.paths) == 1, "one connection for every reply"
    assert fake.paths[0].startswith("/v1/text-to-dialogue/stream-input?")
    for part in ("model_id=eleven_v4_turbo", "output_format=pcm_24000", "sync_alignment=true"):
        assert part in fake.paths[0]
    assert fake.received[0] == {"voices": ["voice123"], "voice_settings": {"stability": 0.4}}
    inputs = [m["inputs"][0] for m in fake.received if "inputs" in m]
    assert inputs == [{"text": "Klar, mach ich. ", "voice_id": "voice123", "new_turn": True},
                      {"text": "Morgen um zehn. ", "voice_id": "voice123", "new_turn": False},
                      {"text": "Noch was. ", "voice_id": "voice123", "new_turn": True}]
    assert all(m.get("flush") for m in fake.received if "inputs" in m), "each piece starts at once"


def test_v4_barge_in_drops_the_connection_and_the_next_reply_gets_a_fresh_one(tmp_path):
    fake = FakeDialogue(hold=True)

    async def run():
        server = await serve(fake.handler, "127.0.0.1", 0)
        async with server:
            voice = voice_for(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", tmp_path,
                              model="eleven_v4_turbo")
            stream = voice.stream()
            stream.send("Das ist ein langer Satz.")
            await asyncio.sleep(0.1)
            stream.cancel()
            assert await collect(stream) == []
            await asyncio.sleep(0.1)
            fake.hold = False
            await fake.release()  # the old socket is gone: nothing of this reaches anyone
            nxt = voice.stream()
            nxt.send("Okay.")
            nxt.finish()
            items = await collect(nxt)
            await voice.close()
            return items

    items = asyncio.run(run())
    assert len(fake.paths) == 2, "the cut-off reply's socket was dropped, a new one opened"
    assert message_numbers(items)[-1] == (0, set())
    assert set().union(*(n for _, n in message_numbers(items))) == {2}, "nothing of the cut-off reply leaks in"


def test_v4_idle_connection_gets_keep_alives(tmp_path, monkeypatch):
    monkeypatch.setattr(elevenlabs, "KEEP_ALIVE_S", 0.05)
    fake = FakeDialogue()

    async def run():
        server = await serve(fake.handler, "127.0.0.1", 0)
        async with server:
            voice = voice_for(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", tmp_path,
                              model="eleven_v4_turbo")
            stream = voice.stream()
            stream.send("Hallo.")
            stream.finish()
            await collect(stream)
            await asyncio.sleep(0.2)
            await voice.close()

    asyncio.run(run())
    assert {"keep_alive": True} in fake.received


def test_v4_error_from_the_server_is_voice_unavailable(tmp_path):
    async def refuse(ws):
        await ws.recv()
        await ws.send(json.dumps({"message": "First message must include 'voices'", "error": "missing_voices",
                                  "code": 1008}))
        await ws.close(1008)

    async def run():
        server = await serve(refuse, "127.0.0.1", 0)
        async with server:
            voice = voice_for(f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}", tmp_path,
                              model="eleven_v4_turbo")
            stream = voice.stream()
            stream.send("Hallo.")
            with pytest.raises(VoiceUnavailable, match="voices"):
                await collect(stream)
            await voice.close()

    asyncio.run(run())


def test_options_are_checked():
    with pytest.raises(ConfigError, match="speed"):
        ElevenLabsOptions(speed=2.0)
    with pytest.raises(ConfigError, match="voice_id"):
        ElevenLabsOptions(voice_id=" ")
