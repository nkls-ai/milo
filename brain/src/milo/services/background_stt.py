"""The one seam where meeting notes share the STT thread with dictation and talk.

The STT executor has a single thread and runs jobs in order. Meeting passes go in only while nobody is
dictating, talking to Milo or waiting for a transcription (`busy()`), and one at a time. When a key goes down
anyway while one runs or waits on the thread, yield_now() ends it with Interrupted (Transcriber.interrupt), so the
user's own passes never wait on a meeting; the meeting service runs that pass again once the user is done.
Live dictation and talk never go through here.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import Executor
from typing import TypeVar

from milo.core.types import Interrupted

T = TypeVar("T")

POLL_S = 0.2
AGAIN_S = 0.05
"""A pass that just started clears the interrupt left over from before it, so a yield that lands in that moment
is sent once more."""


class BackgroundStt:
    def __init__(self, executor: Executor, busy: Callable[[], bool] = lambda: False, *,
                 interrupt: Callable[[], None] = lambda: None, poll_s: float = POLL_S):
        self._executor = executor
        self._busy = busy
        self._interrupt = interrupt
        self._poll_s = poll_s
        self._one = asyncio.Lock()
        self._lock = threading.Lock()
        self._queued = 0  # the background call on the thread (queued or running), 0 when none
        self._running = 0
        self._yielded = False
        self._calls = 0

    async def run(self, fn: Callable[..., T], *args) -> T:
        """Run fn(*args) on the STT thread once it's free of live work. Waits as long as that takes.
        Raises Interrupted if the user needed the thread first (yield_now)."""
        async with self._one:
            while self._busy():
                await asyncio.sleep(self._poll_s)
            with self._lock:
                self._calls += 1
                call = self._calls
                self._queued = call
                self._yielded = False
            try:
                return await asyncio.get_running_loop().run_in_executor(self._executor, self._call, call, fn, args)
            finally:
                with self._lock:
                    self._queued = 0

    def _call(self, call: int, fn: Callable[..., T], args: tuple) -> T:
        with self._lock:
            if self._yielded:
                raise Interrupted()
            self._running = call
        try:
            return fn(*args)
        finally:
            with self._lock:
                self._running = 0

    def yield_now(self) -> None:
        """A dictate or talk key went down: end the background call on the STT thread, or keep it from starting,
        so the user's passes run next. Call on the event loop, before queueing the user's work."""
        with self._lock:
            if not self._queued:
                return
            self._yielded = True
            running = self._running
            if running:
                self._interrupt()
        if running:
            asyncio.get_running_loop().call_later(AGAIN_S, self._again, running)

    def _again(self, call: int) -> None:
        with self._lock:
            if self._running == call:
                self._interrupt()

    async def now(self, fn: Callable[..., T], *args) -> T:
        """Run fn(*args) next on the STT thread, for something the user waits on (a question during the call)."""
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn, *args)
