"""Proactive behavior that costs nothing: heartbeat engine, daily LLM budget, rules by name."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from milo.core.ports import ProactiveEngine, ReminderSource
from milo.core.registry import RULES, AdapterContext, ConfigError, options_from

from .engine import STATE_FILE, HeartbeatEngine, HeartbeatOptions


def build_engine(section: Mapping[str, Any], ctx: AdapterContext, reminders: ReminderSource) -> ProactiveEngine:
    """Build the engine from the whole [heartbeat] table. `enabled` is compose.py's business."""
    from . import rules as _builtin  # noqa: F401  registers the built-in rules

    scalars = {k: v for k, v in section.items() if not isinstance(v, Mapping)}
    tables = {k: v for k, v in section.items() if isinstance(v, Mapping)}
    options = options_from(HeartbeatOptions, scalars, "heartbeat")
    unknown = sorted(set(tables) - set(RULES.names()))
    if unknown:
        raise ConfigError(f"unknown table(s) {', '.join(f'[heartbeat.{t}]' for t in unknown)}; "
                          f"available rules: {', '.join(RULES.names())}")
    dupes = sorted({n for n in options.rules if options.rules.count(n) > 1})
    if dupes:
        raise ConfigError(f"[heartbeat] rules lists {', '.join(dupes)} more than once")
    rules = [RULES.create(name, tables.get(name, {}), ctx) for name in options.rules]
    return HeartbeatEngine(rules, options, reminders, ctx.state_dir / STATE_FILE)


__all__ = ["HeartbeatEngine", "HeartbeatOptions", "build_engine"]
