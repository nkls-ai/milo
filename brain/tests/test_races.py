"""Ordering bugs between the event loop, the brain socket and the STT and TTS threads (review finding A8).

The rest of the suite runs every executor inline (tests/services/stack.py), so STT, TTS and memory never
overlap with the event loop, and a bug like H1 (a key press waiting behind a transcription) can't show there.
These tests use the real socket and `Stack(real_threads=True)`, with engines that take real time, and measure
how long the user waits.
"""

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from milo.core.events import Confirm
from milo.transport.unix_socket import UnixSocketServer
from tests.fakes import FakeTranscriber, FakeVoice
from tests.services.stack import Stack

SLOW_S = 1.0
PROMPT_S = 0.3
"""What the user may wait for something they did: well under SLOW_S, with room for a busy machine."""


class SlowTranscriber(FakeTranscriber):
    """A 60 s recording with `stream = "off"`, or a paged-out model."""

    def transcribe(self, audio, before="", *, quick=False):
        time.sleep(SLOW_S)
        return super().transcribe(audio, before, quick=quick)


class SlowVoice(FakeVoice):
    def synthesize(self, text):
        time.sleep(SLOW_S)
        return super().synthesize(text)


@pytest.fixture
def sock_path():
    root = Path(tempfile.mkdtemp(dir="/tmp", prefix="milo-"))  # macOS caps socket paths at 104 bytes
    try:
        yield root / "run" / "brain.sock"
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def connect(s: Stack, path: Path):
    server = UnixSocketServer(path, s.brain.handle, s.brain.greeting)
    await server.start()
    reader, writer = await asyncio.open_unix_connection(str(path))

    async def send(message: dict) -> float:
        writer.write(json.dumps(message).encode() + b"\n")
        await writer.drain()
        return time.monotonic()

    async def close():
        writer.close()
        await server.close()
        s.close()

    return send, close


def test_a_yes_while_milo_speaks_the_question_counts_at_once(sock_path):
    # The question is spoken on the TTS thread, which takes a second here; the click comes in over the socket
    # meanwhile and must not wait for the voice.
    s = Stack(voice=SlowVoice(), real_threads=True)

    async def run():
        send, close = await connect(s, sock_path)
        asking = asyncio.create_task(s.approvals.confirm("Send this to Anna?"))
        await asyncio.sleep(0.1)
        [question] = s.sink.of(Confirm)
        clicked = await send({"type": "confirm_answer", "id": question.id, "yes": True})
        yes = await asyncio.wait_for(asking, 3)
        waited = time.monotonic() - clicked
        await close()
        return yes, waited

    yes, waited = asyncio.run(run())
    assert yes and waited < PROMPT_S, f"the yes counted {waited:.2f} s after the click"


# H1 (docs/review/2026-10-30.md): track 1 fixed it; listen_stop no longer holds the command loop.
def test_a_key_press_right_after_a_release_opens_the_mic_at_once(sock_path):
    # The user lets go and presses again to go on dictating. The first recording's transcription takes a
    # second on the STT thread; the second press must open the mic now, or its first words are lost.
    s = Stack(transcriber=SlowTranscriber("first", "second"), real_threads=True)
    opened: list[float] = []
    start = s.mic.start
    s.mic.start = lambda callback: (opened.append(time.monotonic()), start(callback))[1]

    async def run():
        send, close = await connect(s, sock_path)
        await send({"type": "listen_start", "mode": "dictate"})
        await asyncio.sleep(0.05)
        await send({"type": "listen_stop"})
        await asyncio.sleep(0.05)
        pressed = await send({"type": "listen_start", "mode": "dictate"})
        await asyncio.sleep(SLOW_S + 0.5)
        await close()
        return pressed

    pressed = asyncio.run(run())
    assert len(opened) == 2 and opened[1] - pressed < PROMPT_S, \
        f"the mic opened {opened[1] - pressed:.2f} s after the key went down"


def test_a_request_to_an_app_that_quits_fails_when_it_quits_not_at_the_timeout(sock_path):
    # Over the real socket: the app reads the request and quits. The caller learns that when the connection
    # drops, not after the bridge's 30 s timeout (M3).
    from milo.services.app_bridge import APP_LEFT_WORDS, AppBridge, AppError

    s = Stack(real_threads=True)

    async def run():
        server = UnixSocketServer(sock_path, s.brain.handle, s.brain.greeting)
        bridge = AppBridge(server, timeout_s=30)
        server.on_client_gone.append(bridge.app_gone)
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        await asyncio.sleep(0.05)
        calling = asyncio.create_task(bridge.call("calendar.events", {"start": "2026-10-30T00:00"}))
        while json.loads(await asyncio.wait_for(reader.readline(), 2)).get("type") != "app_request":
            pass
        writer.close()
        quit_at = time.monotonic()
        with pytest.raises(AppError) as failed:
            await asyncio.wait_for(calling, 5)
        waited = time.monotonic() - quit_at
        await server.close()
        s.close()
        return str(failed.value), waited

    words, waited = asyncio.run(run())
    assert words == APP_LEFT_WORDS and waited < PROMPT_S, f"failed {waited:.2f} s after the app quit"
