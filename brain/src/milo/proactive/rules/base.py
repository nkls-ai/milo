"""Shared bits for heartbeat rules."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from milo.core.registry import ConfigError
from milo.core.types import Signals

ACTIVE_IDLE_S = 120
"""Below this many seconds without input the user counts as at the keyboard."""


def is_active(signals: Signals) -> bool:
    return signals.idle_s < ACTIVE_IDLE_S


@runtime_checkable
class Observer(Protocol):
    """Optional hook for rules that track the user over time (last seen, time in one app).

    The engine calls `observe` on every tick after the checks, even on ticks where the rule was
    gated off (user away, quiet app), so the tracking never misses an idle gap or an app switch.
    """

    def observe(self, signals: Signals) -> None: ...


def check_hours(section: str, **hours: int) -> None:
    for key, value in hours.items():
        if not 0 <= value <= 24:
            raise ConfigError(f"[{section}] {key} must be between 0 and 24, got {value}")
