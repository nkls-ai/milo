"""Say hi in the bubble when the user comes back after a while away."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from milo.core.registry import RULES, AdapterContext, ConfigError, options_from
from milo.core.times import local
from milo.core.types import Emotion, Nudge, Reminder, Signals

from .base import is_active


@dataclass(frozen=True)
class WelcomeBackOptions:
    away_min: float = 30

    def __post_init__(self):
        if self.away_min <= 0:
            raise ConfigError("[heartbeat.welcome_back] away_min must be > 0")


class WelcomeBackRule:
    name = "welcome_back"
    user_requested = False

    def __init__(self, options: WelcomeBackOptions):
        self.options = options
        self.state: dict = {}

    def check(self, signals: Signals, reminders: list[Reminder]) -> list[Nudge]:
        last = self.state.get("last_active")
        if not last or signals.now - local(last) < timedelta(minutes=self.options.away_min):
            return []
        return [Nudge(self.name, Emotion.HAPPY, "Welcome back!", speak=False)]

    def observe(self, signals: Signals) -> None:
        # Runs after check, so check compares against the previous active tick.
        if is_active(signals):
            self.state["last_active"] = signals.now.isoformat()


@RULES.register("welcome_back")
def _welcome_back(options: Mapping[str, Any], ctx: AdapterContext) -> WelcomeBackRule:
    return WelcomeBackRule(options_from(WelcomeBackOptions, options, "heartbeat.welcome_back"))
