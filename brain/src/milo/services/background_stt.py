"""The one seam where meeting notes share the STT thread with dictation and talk.

The STT executor has a single thread and runs jobs in order. Meeting passes go in only while nobody is
dictating, talking to Milo or waiting for a transcription (`busy()`), and one at a time, so a dictation started
during a call waits at most for the pass already running. Live dictation and talk never go through here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import Executor
from typing import TypeVar

T = TypeVar("T")

POLL_S = 0.2


class BackgroundStt:
    def __init__(self, executor: Executor, busy: Callable[[], bool] = lambda: False, *, poll_s: float = POLL_S):
        self._executor = executor
        self._busy = busy
        self._poll_s = poll_s
        self._one = asyncio.Lock()

    async def run(self, fn: Callable[..., T], *args) -> T:
        """Run fn(*args) on the STT thread once it's free of live work. Waits as long as that takes."""
        async with self._one:
            while self._busy():
                await asyncio.sleep(self._poll_s)
            return await asyncio.get_running_loop().run_in_executor(self._executor, fn, *args)

    async def now(self, fn: Callable[..., T], *args) -> T:
        """Run fn(*args) next on the STT thread, for something the user waits on (a question during the call)."""
        return await asyncio.get_running_loop().run_in_executor(self._executor, fn, *args)
