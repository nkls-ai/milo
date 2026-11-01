from tests.local_transport import short_tempdir
from tests.local_transport import connect as local_connect
"""A key press right after a release: the mic opens at once, and the texts come out in recording order.

These run the STT on real threads (the Stack's inline executor can't show waits like these) and one of them
goes through the real socket, the way the app sends its commands."""

import asyncio
import json
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from milo.core.events import Dictation, StateChanged
from milo.core.types import ListenMode, MiloState
from milo.services.listening import _InOrder
from milo.transport.unix_socket import UnixSocketServer
from tests.fakes import FakeTranscriber
from tests.services.stack import Stack, until


class GatedTranscriber(FakeTranscriber):
    """Transcription number i returns texts[i] once gates[i] is set (or after `wait_s` without a gate)."""

    def __init__(self, *texts: str, wait_s: float = 0.0, gated: bool = False):
        super().__init__(*texts)
        self.answers = list(texts)
        self.gates = [threading.Event() for _ in texts]
        self.wait_s = wait_s
        self.gated = gated

    def transcribe(self, audio, before: str = "", *, quick: bool = False) -> str:
        i = len(self.calls)
        self.calls.append(audio)
        if self.gated:
            self.gates[i].wait(5)
        else:
            time.sleep(self.wait_s)
        return self.answers[i]


def threaded(transcriber: FakeTranscriber, workers: int = 1) -> tuple[Stack, ThreadPoolExecutor]:
    s = Stack(transcriber=transcriber)
    executor = ThreadPoolExecutor(workers)
    s.listening._executor = executor
    return s, executor


def test_a_key_press_right_after_a_release_opens_the_mic_at_once_over_the_socket():
    s, executor = threaded(GatedTranscriber("First one.", "Second one.", wait_s=1.0))  # a slow, paged-out model
    path = Path(tempfile.mkdtemp(dir=short_tempdir, prefix="milo-")) / "run" / "brain.sock"  # short: 104 bytes at most
    starts: list[float] = []
    start = s.mic.start
    s.mic.start = lambda on_level: (starts.append(time.monotonic()), start(on_level))[1]

    async def run() -> float:
        server = UnixSocketServer(path, s.brain.handle, s.brain.greeting)
        await server.start()
        _, writer = await local_connect(path)

        async def send(message: dict) -> float:
            writer.write((json.dumps(message) + "\n").encode())
            await writer.drain()
            return time.monotonic()

        await send({"type": "listen_start", "mode": "dictate"})
        await until(lambda: len(starts) == 1)
        await send({"type": "listen_stop"})
        await asyncio.sleep(0.2)
        pressed = await send({"type": "listen_start", "mode": "dictate"})  # the user goes on at once
        await until(lambda: len(starts) == 2)
        latency = starts[1] - pressed
        await send({"type": "listen_stop"})
        await until(lambda: len(s.sink.of(Dictation)) == 2)
        writer.close()
        await server.close()
        return latency

    try:
        latency = asyncio.run(run())
    finally:
        executor.shutdown()
        shutil.rmtree(path.parent.parent, ignore_errors=True)
    assert latency < 0.1, f"the mic opened {latency:.2f}s after the key went down"
    assert [d.text for d in s.sink.of(Dictation)] == ["FIRST ONE.", "SECOND ONE."]


def test_a_quick_second_dictation_never_pastes_before_a_slow_first_one():
    s, executor = threaded(GatedTranscriber("First one.", "Second one.", gated=True), workers=2)

    async def run():
        s.listening.start(ListenMode.DICTATE)
        first = s.listening.release()
        s.listening.start(ListenMode.DICTATE)
        second = s.listening.release()
        await until(lambda: len(s.transcriber.calls) == 2)
        s.transcriber.gates[1].set()  # the second is done first
        await second
        assert s.sink.of(Dictation) == [], "held back until the first is out"
        s.transcriber.gates[0].set()
        await first
        await until(lambda: len(s.sink.of(Dictation)) == 2)

    asyncio.run(run())
    executor.shutdown()
    assert [d.text for d in s.sink.of(Dictation)] == ["FIRST ONE.", "SECOND ONE."]
    assert s.ui.state is MiloState.IDLE


def test_an_older_release_does_not_end_the_state_of_a_newer_recording():
    s, executor = threaded(GatedTranscriber("First one.", "Second one.", gated=True))

    async def run():
        s.listening.start(ListenMode.DICTATE)
        first = s.listening.release()
        s.listening.start(ListenMode.DICTATE)  # dictating again while the first is transcribed
        s.transcriber.gates[0].set()
        await first
        assert s.ui.state is MiloState.DICTATING, "the newer recording still shows"
        second = s.listening.release()
        assert s.ui.state is MiloState.TRANSCRIBING
        s.transcriber.gates[1].set()
        await second

    asyncio.run(run())
    executor.shutdown()
    assert s.ui.state is MiloState.IDLE
    states = [e.state for e in s.sink.of(StateChanged)]
    assert states[-1] is MiloState.IDLE and states.count(MiloState.IDLE) == 1, states


def test_a_cancelled_recording_lets_the_ones_after_it_through():
    s, executor = threaded(GatedTranscriber("First one.", "Third one.", gated=True))

    async def run():
        s.listening.start(ListenMode.DICTATE)
        first = s.listening.release()
        s.listening.start(ListenMode.DICTATE, tentative=True)
        s.listening.cancel()  # a stray tap
        s.listening.start(ListenMode.DICTATE)
        third = s.listening.release()
        for gate in s.transcriber.gates:
            gate.set()
        await first
        await third
        await until(lambda: len(s.sink.of(Dictation)) == 2)

    asyncio.run(run())
    executor.shutdown()
    assert [d.text for d in s.sink.of(Dictation)] == ["FIRST ONE.", "THIRD ONE."]
    assert s.ui.state is MiloState.IDLE


def test_in_order_holds_results_until_the_one_before_is_closed():
    out: list[str] = []
    a = _InOrder(None)
    b = _InOrder(a)
    c = _InOrder(b)
    c.run(lambda: out.append("c1"))
    b.run(lambda: out.append("b1"))
    c.close()
    a.run(lambda: out.append("a1"))
    assert out == ["a1"]
    b.run(lambda: out.append("b2"))
    a.close()
    assert out == ["a1", "b1", "b2"]
    b.close()
    assert out == ["a1", "b1", "b2", "c1"] and c.closed
    d = _InOrder(c)
    d.run(lambda: out.append("d1"))
    assert out[-1] == "d1", "nothing before it is open: straight through"
