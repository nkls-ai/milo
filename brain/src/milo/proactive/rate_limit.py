"""Spoken nudges interrupt the user, so they get a minimum gap and an hourly cap."""

from __future__ import annotations

from datetime import datetime, timedelta

from milo.core.times import local

_HOUR = timedelta(hours=1)


class RateLimiter:
    """Decides whether a spoken voluntary nudge may go out now.

    `state` is the engine's "rate_limit" dict, mutated in place, so recent nudge times survive a
    restart and restarting Milo can't be used to get around the cap.
    """

    def __init__(self, min_gap: timedelta, per_hour: int, state: dict):
        self.min_gap = min_gap
        self.per_hour = per_hour
        self.state = state

    def take(self, now: datetime) -> bool:
        """True if a nudge may go out now; records it. False leaves the record unchanged."""
        recent = [t for t in self._times() if t <= now and now - t < _HOUR]
        too_soon = bool(recent) and now - max(recent) < self.min_gap
        allowed = not too_soon and len(recent) < self.per_hour
        if allowed:
            recent.append(now)
        self.state["times"] = [t.isoformat() for t in recent]
        return allowed

    def _times(self) -> list[datetime]:
        out = []
        for raw in self.state.get("times", []):
            try:
                out.append(local(raw))
            except (TypeError, ValueError):
                continue
        return out
