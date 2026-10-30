"""Greet the user once when they first sit down in the morning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from milo.core.registry import RULES, AdapterContext, ConfigError, options_from
from milo.core.types import Emotion, Nudge, Reminder, Signals

from .base import check_hours


@dataclass(frozen=True)
class MorningOptions:
    after_hour: int = 5
    before_hour: int = 12

    def __post_init__(self):
        check_hours("heartbeat.morning", after_hour=self.after_hour, before_hour=self.before_hour)
        if self.after_hour >= self.before_hour:
            raise ConfigError("[heartbeat.morning] after_hour must be before before_hour")


class MorningRule:
    name = "morning"
    user_requested = False

    def __init__(self, options: MorningOptions):
        self.options = options
        self.state: dict = {}

    def check(self, signals: Signals, reminders: list[Reminder]) -> list[Nudge]:
        now, today = signals.now, signals.now.date().isoformat()
        if self.state.get("greeted_on") == today or not self.options.after_hour <= now.hour < self.options.before_hour:
            return []
        self.state["greeted_on"] = today
        todays = sorted((r for r in reminders if not r.done and r.due.date() == now.date()), key=lambda r: r.due)
        return [Nudge(self.name, Emotion.HAPPY, _template(todays), speak=True, llm_prompt=_prompt(todays))]


def _template(todays: list[Reminder]) -> str:
    """The wording used when the budget allows no LLM call, which by default is always."""
    if not todays:
        return "Good morning! I'm here if you need me."
    count = "one reminder" if len(todays) == 1 else f"{len(todays)} reminders"
    return f"Good morning! You have {count} today, the first at {todays[0].due:%H:%M}."


def _prompt(todays: list[Reminder]) -> str:
    listed = "; ".join(f"{r.due:%H:%M} {r.text}" for r in todays) or "none"
    return ("It is morning and the user just sat down. Greet them in one short sentence. "
            f"Mention today's reminders if there are any. Today's reminders: {listed}.")


@RULES.register("morning")
def _morning(options: Mapping[str, Any], ctx: AdapterContext) -> MorningRule:
    return MorningRule(options_from(MorningOptions, options, "heartbeat.morning"))
