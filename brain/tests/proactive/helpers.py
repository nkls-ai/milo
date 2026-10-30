"""Builds engines the way compose.py will: from a [heartbeat] table and an AdapterContext."""

from __future__ import annotations

import copy
import tomllib
from datetime import datetime
from importlib import resources
from pathlib import Path

from milo.core.registry import AdapterContext
from milo.core.types import Signals
from milo.proactive import build_engine
from tests.fakes import FakeClock, ListReminders

AM = datetime(2026, 10, 29, 8, 0)
PM = datetime(2026, 10, 29, 13, 0)


def default_section() -> dict:
    """The [heartbeat] table exactly as shipped in the workspace template."""
    text = (resources.files("milo") / "workspace_template" / "config.toml").read_text()
    return copy.deepcopy(tomllib.loads(text)["heartbeat"])


def engine(tmp_path: Path, reminders=None, **overrides):
    """An engine over the default section. `overrides` replace top-level keys or whole sub-tables."""
    section = default_section()
    section.update(overrides)
    ctx = AdapterContext(home=tmp_path, state_dir=tmp_path / "state", clock=FakeClock())
    return build_engine(section, ctx, reminders or ListReminders())


def sig(t: datetime, idle_s: float = 5, app: str | None = "Safari") -> Signals:
    return Signals(t, idle_s, app)
