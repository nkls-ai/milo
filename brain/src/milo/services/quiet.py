from __future__ import annotations

import asyncio
from collections.abc import Callable

POLL_S = 0.2


async def wait_while(busy: Callable[[], bool], timeout_s: float, poll_s: float = POLL_S) -> bool:
    """Wait until busy() is False, for at most timeout_s. True if it became free, False on timeout.

    For things Milo says unprompted (task results, nudges): they wait for the user's turn to end instead
    of cutting Milo off mid-answer.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while busy():
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(poll_s)
    return True
