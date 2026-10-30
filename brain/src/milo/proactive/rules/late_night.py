"""Note, once per night and without speaking, that it's very late."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from milo.core.registry import RULES, AdapterContext, ConfigError, options_from
from milo.core.types import Emotion, Nudge, Reminder, Signals

from .base import check_hours


@dataclass(frozen=True)
class LateNightOptions:
    # A window like 23..4 wraps past midnight.
    from_hour: int = 1
    until_hour: int = 5

    def __post_init__(self):
        check_hours("heartbeat.late_night", from_hour=self.from_hour, until_hour=self.until_hour)
        if self.from_hour == self.until_hour:
            raise ConfigError("[heartbeat.late_night] from_hour and until_hour must differ")


class LateNightRule:
    name = "late_night"
    user_requested = False

    def __init__(self, options: LateNightOptions):
        self.options = options
        self.state: dict = {}

    def check(self, signals: Signals, reminders: list[Reminder]) -> list[Nudge]:
        hour, o = signals.now.hour, self.options
        inside = o.from_hour <= hour < o.until_hour if o.from_hour < o.until_hour else (hour >= o.from_hour or hour < o.until_hour)
        # Shifting by until_hour gives every hour of one night the same date, even across midnight.
        night = (signals.now - timedelta(hours=o.until_hour)).date().isoformat()
        if not inside or self.state.get("night_of") == night:
            return []
        self.state["night_of"] = night
        return [Nudge(self.name, Emotion.SLEEPY, "It's getting really late...", speak=False)]


@RULES.register("late_night")
def _late_night(options: Mapping[str, Any], ctx: AdapterContext) -> LateNightRule:
    return LateNightRule(options_from(LateNightOptions, options, "heartbeat.late_night"))
