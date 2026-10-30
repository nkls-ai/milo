"""When Milo sleeps: the nightly consolidation runs once per finished day, while the user is away and the Mac is
plugged in, within a daily cap on worker calls. Like the heartbeat, a check costs nothing: it reads the clock,
the idle time and the power source.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol

from milo.core.ports import Clock, Consolidator

from .context import UserContext

log = logging.getLogger("milo.sleep")

CHECK_S = 600.0
IDLE_S = 20 * 60
"""The user has been away this long."""
DAYS_BACK = 3
"""Days missed (the Mac was off or busy) are caught up this far back, oldest first."""


class SleepState(Protocol):
    """state/sleep.json: {"done": [days], "calls": {day: n}}. Mutated in place, then saved."""

    data: dict

    def save(self) -> None: ...


class SleepRunner:
    def __init__(self, consolidator: Consolidator, context: UserContext, clock: Clock, state: SleepState, *,
                 calls_per_day: int, on_power: Callable[[], bool], busy: Callable[[], bool] = lambda: False,
                 after: Callable[[], None] = lambda: None, check_s: float = CHECK_S, idle_s: float = IDLE_S):
        self._consolidator = consolidator
        self._context = context
        self._clock = clock
        self._state = state
        self.calls_per_day = calls_per_day
        self._on_power = on_power
        self._busy = busy
        self._after = after
        """Called after each check, e.g. to let the index catch up with lines another process wrote."""
        self._check_s = check_s
        self._idle_s = idle_s

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self._check_s)
            try:
                await self.check()
            except Exception:
                log.exception("the nightly consolidation check failed")
            self._after()

    def due(self) -> date | None:
        """The oldest finished day not consolidated yet, if Milo may sleep now."""
        today = self._clock.now().date()
        if self._calls(today) >= self.calls_per_day:
            return None
        done = set(self._state.data.get("done", []))
        days = [today - timedelta(days=n) for n in range(DAYS_BACK, 0, -1)]
        day = next((d for d in days if d.isoformat() not in done), None)
        if day is None or self._busy() or self._context.idle_s() < self._idle_s:
            return None
        if not self._on_power():
            return None
        return day

    async def check(self) -> bool:
        """Consolidate one day if it is time. Returns whether a day was done (or found empty)."""
        day = self.due()
        if day is None:
            return False
        today = self._clock.now().date()
        log.info("sleeping on %s", day)
        report = await self._consolidator.consolidate(day)
        data = self._state.data
        if report.calls:
            calls = {today.isoformat(): self._calls(today) + report.calls}
            data["calls"] = calls  # only today's count is kept
        finished = not report.skipped or report.skipped in ("nothing happened", "dry run")
        if finished:
            keep = {(today - timedelta(days=n)).isoformat() for n in range(DAYS_BACK + 1)}
            data["done"] = sorted({*data.get("done", []), day.isoformat()} & keep)
        self._state.save()
        log.info("slept on %s: %s", day, report.skipped or f"{report.episodes} summaries, {len(report.changes)} changes")
        return finished

    def _calls(self, today: date) -> int:
        return int(self._state.data.get("calls", {}).get(today.isoformat(), 0))
