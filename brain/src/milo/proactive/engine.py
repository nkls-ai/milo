"""The heartbeat engine: runs local rules on cheap signals, with zero harness calls per tick.

A tick stats reminders.md, runs the rules in memory and writes state/heartbeat.json. Nudges can
carry an `llm_prompt`, but only the runner may act on it, and only if `budget.allow()` says so.
"""

from __future__ import annotations

from milo import system

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

from milo.core.ports import ProactiveRule, ReminderSource
from milo.core.registry import ConfigError
from milo.core.types import Nudge, Signals

from .budget import DailyBudget
from .rate_limit import RateLimiter
from .rules.base import Observer, is_active

log = logging.getLogger(__name__)

STATE_FILE = "heartbeat.json"


@dataclass(frozen=True)
class HeartbeatOptions:
    """The scalar keys of [heartbeat]. Sub-tables belong to the rules."""

    enabled: bool = True
    tick_s: float = 30
    llm_calls_per_day: int = 0
    min_gap_between_nudges_min: float = 20
    max_nudges_per_hour: int = 2
    quiet_apps: tuple[str, ...] = ("zoom.us", "FaceTime", "Microsoft Teams", "Webex", "Keynote")
    rules: tuple[str, ...] = ("reminders", "morning", "late_night", "welcome_back", "focus_break")

    def __post_init__(self):
        if self.tick_s <= 0:
            raise ConfigError("[heartbeat] tick_s must be > 0")
        for key in ("llm_calls_per_day", "min_gap_between_nudges_min", "max_nudges_per_hour"):
            if getattr(self, key) < 0:
                raise ConfigError(f"[heartbeat] {key} must be >= 0")


class HeartbeatEngine:
    """ProactiveEngine. Owns gating, the rate limit, the daily LLM budget and heartbeat.json.

    Rules run in the order given, which is also their precedence: the first voluntary rule that
    returns a nudge wins the tick. User-requested rules (reminders) always run.
    """

    def __init__(self, rules: Sequence[ProactiveRule], options: HeartbeatOptions,
                 reminders: ReminderSource, state_path: Path):
        self.rules = list(rules)
        self.tick_s = float(options.tick_s)
        self.quiet_apps = frozenset(options.quiet_apps)
        self.reminders = reminders
        self.state_path = state_path
        saved = _load(state_path)
        saved_rules = _dict(saved.get("rules"))
        for rule in self.rules:
            state = saved_rules.get(rule.name)
            if isinstance(state, dict):
                rule.state = state
        self.budget = DailyBudget(options.llm_calls_per_day, _dict(saved.get("budget")), on_change=self.save)
        self.limiter = RateLimiter(timedelta(minutes=options.min_gap_between_nudges_min),
                                   options.max_nudges_per_hour, _dict(saved.get("rate_limit")))

    def tick(self, signals: Signals) -> list[Nudge]:
        active = is_active(signals)
        quiet = signals.app in self.quiet_apps
        reminders = self.reminders.all()
        out: list[Nudge] = []
        voluntary_taken = False
        for rule in self.rules:
            if rule.user_requested:
                nudges = self._check(rule, signals, reminders)
                out += [replace(n, speak=False) for n in nudges] if quiet else nudges
            elif active and not quiet and not voluntary_taken:
                nudges = self._check(rule, signals, reminders)[:1]
                if nudges:
                    # The winning rule keeps the tick even if the rate limit drops its nudge,
                    # so a lower-precedence rule never speaks in its place.
                    voluntary_taken = True
                    out += [n for n in nudges if not n.speak or self.limiter.take(signals.now)]
        # Trackers see every tick, including ticks where their rule was gated off.
        for rule in self.rules:
            if isinstance(rule, Observer):
                try:
                    rule.observe(signals)
                except Exception:
                    log.exception("heartbeat rule %s failed to observe", rule.name)
        self.save()
        return out

    def save(self) -> None:
        """Atomic write, so a crash mid-save never leaves a half-written file."""
        data = {
            "rules": {r.name: r.state for r in self.rules},
            "budget": self.budget.state,
            "rate_limit": self.limiter.state,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        system.replace_file(tmp, self.state_path)

    @staticmethod
    def _check(rule: ProactiveRule, signals: Signals, reminders) -> list[Nudge]:
        # One broken rule must not take reminders down with it.
        try:
            return list(rule.check(signals, reminders))
        except Exception:
            log.exception("heartbeat rule %s failed", rule.name)
            return []


def _load(path: Path) -> dict:
    try:
        return _dict(json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}
