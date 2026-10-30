from __future__ import annotations

from milo.core.ports import Clock

CONTEXT_STALE_S = 120


class UserContext:
    """The latest ContextUpdate from the app (frontmost app, idle time), aged by the clock."""

    def __init__(self, clock: Clock, stale_s: float = CONTEXT_STALE_S):
        self._clock = clock
        self._stale_s = stale_s
        self.app: str | None = None
        self._idle_s = 0.0
        self._reported_at: float | None = None

    def update(self, app: str | None, idle_s: float) -> None:
        self.app = app
        self._idle_s = idle_s
        self._reported_at = self._clock.monotonic()

    def idle_s(self) -> float:
        """Reported idle plus the time since the report. inf if the app stopped reporting: nobody is there."""
        if self._reported_at is None:
            return float("inf")
        since = self._clock.monotonic() - self._reported_at
        return float("inf") if since > self._stale_s else self._idle_s + since
