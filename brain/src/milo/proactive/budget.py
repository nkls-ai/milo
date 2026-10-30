"""The daily cap on harness calls the heartbeat may make."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date


class DailyBudget:
    """LlmBudget whose counter lives in heartbeat.json, so a restart can't reset the cap.

    `state` is the engine's "budget" dict, mutated in place. Only today's counter is kept.
    """

    def __init__(self, calls_per_day: int, state: dict, on_change: Callable[[], None] | None = None):
        self.calls_per_day = calls_per_day
        self.state = state
        self._on_change = on_change

    def allow(self, today: date) -> bool:
        return self.state.get(today.isoformat(), 0) < self.calls_per_day

    def spend(self, today: date) -> None:
        key = today.isoformat()
        count = int(self.state.get(key, 0)) + 1
        self.state.clear()
        self.state[key] = count
        if self._on_change:
            self._on_change()
