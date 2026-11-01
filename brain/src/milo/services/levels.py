from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from milo.core.events import Level
from milo.core.ports import EventSink, LevelCallback

LEVEL_INTERVAL_S = 0.025  # a cap under the mic's 32 ms blocks, so each block's level gets through (~30 a second)


def throttled_levels(sink: EventSink, loop: asyncio.AbstractEventLoop, *,
                     interval_s: float = LEVEL_INTERVAL_S,
                     monotonic: Callable[[], float] = time.monotonic) -> LevelCallback:
    """A LevelCallback for audio threads: at most one Level per interval, always letting silence through.

    The sink is only safe on the loop thread, so events hop over with call_soon_threadsafe, which
    takes no kwargs: hence the lambda.
    """
    last = -interval_s

    def on_level(value: float) -> None:
        nonlocal last
        now = monotonic()
        if value and now - last < interval_s:
            return
        last = now
        event = Level(round(float(value), 3))
        try:
            loop.call_soon_threadsafe(lambda: sink.emit(event))
        except RuntimeError:
            pass  # loop closed during shutdown

    return on_level
