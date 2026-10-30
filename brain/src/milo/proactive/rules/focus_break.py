"""Suggest a stretch after a long stretch in one app."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from milo.core.registry import RULES, AdapterContext, ConfigError, options_from
from milo.core.types import Emotion, Nudge, Reminder, Signals

RESET_IDLE_S = 300
"""A pause this long counts as a break and restarts the clock."""


@dataclass(frozen=True)
class FocusBreakOptions:
    after_min: float = 90

    def __post_init__(self):
        if self.after_min <= 0:
            raise ConfigError("[heartbeat.focus_break] after_min must be > 0")


class FocusBreakRule:
    name = "focus_break"
    user_requested = False

    def __init__(self, options: FocusBreakOptions):
        self.options = options
        self.state: dict = {}

    def check(self, signals: Signals, reminders: list[Reminder]) -> list[Nudge]:
        # Track first: an app switch this tick must not count toward the new app.
        self.observe(signals)
        if not signals.app:
            return []
        focused = signals.now - datetime.fromisoformat(self.state["since"])
        if focused < timedelta(minutes=self.options.after_min):
            return []
        self.state["since"] = signals.now.isoformat()
        minutes = int(focused.total_seconds() // 60)
        return [Nudge(self.name, Emotion.CONCERNED,
                      f"You've been in {signals.app} for {minutes} minutes. Stretch break?", speak=True)]

    def observe(self, signals: Signals) -> None:
        if signals.app != self.state.get("app") or signals.idle_s >= RESET_IDLE_S or "since" not in self.state:
            self.state["app"] = signals.app
            self.state["since"] = signals.now.isoformat()


@RULES.register("focus_break")
def _focus_break(options: Mapping[str, Any], ctx: AdapterContext) -> FocusBreakRule:
    return FocusBreakRule(options_from(FocusBreakOptions, options, "heartbeat.focus_break"))
