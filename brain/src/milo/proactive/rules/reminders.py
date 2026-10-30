"""Fire reminders.md entries when due. The user asked for these, so they run even in quiet apps."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from milo.core.registry import RULES, AdapterContext, ConfigError, options_from
from milo.core.types import Emotion, Nudge, Reminder, Signals

LATE_AFTER = timedelta(minutes=5)


@dataclass(frozen=True)
class RemindersOptions:
    # Reminders more than this overdue (Milo was off) are dropped silently instead of piling up.
    grace_hours: float = 12

    def __post_init__(self):
        if self.grace_hours < 0:
            raise ConfigError("[heartbeat.reminders] grace_hours must be >= 0")


class RemindersRule:
    name = "reminders"
    user_requested = True

    def __init__(self, options: RemindersOptions):
        self.options = options
        self.state: dict = {}

    def check(self, signals: Signals, reminders: list[Reminder]) -> list[Nudge]:
        now, grace = signals.now, timedelta(hours=self.options.grace_hours)
        fired = set(self.state.get("fired", []))
        out = []
        for r in reminders:
            if r.done or r.id in fired or r.due > now:
                continue
            fired.add(r.id)
            late = now - r.due
            if late > grace:
                continue
            text = f"Reminder from {r.due:%H:%M}: {r.text}" if late > LATE_AFTER else f"Reminder: {r.text}"
            out.append(Nudge(self.name, Emotion.EXCITED, text, speak=True))
        # Keep only ids still in the file so the list doesn't grow forever.
        self.state["fired"] = sorted(fired & {r.id for r in reminders})
        return out


@RULES.register("reminders")
def _reminders(options: Mapping[str, Any], ctx: AdapterContext) -> RemindersRule:
    return RemindersRule(options_from(RemindersOptions, options, "heartbeat.reminders"))
