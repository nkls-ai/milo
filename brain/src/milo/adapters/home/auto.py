"""`[home] use = "auto"`, the default: Home Assistant when `[home.home_assistant]` has a url, else Apple Home where
this computer has the `shortcuts` command, else no home (ADR 0037). And `none`.

compose hands "auto" every `[home.*]` table, so it can build the one it picks with that one's own options.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from typing import Any

from milo.core.ports import Home
from milo.core.registry import HOMES, AdapterContext, ConfigError


@HOMES.register("auto")
def _auto(options: Mapping[str, Any], ctx: AdapterContext) -> Home | None:
    for name, table in options.items():
        if not isinstance(table, dict):
            raise ConfigError(f"[home] {name} must be a table, like [home.{name}]")
    if options.get("home_assistant", {}).get("url"):
        return HOMES.create("home_assistant", options["home_assistant"], ctx)
    if shutil.which("shortcuts"):
        return HOMES.create("apple_home", options.get("apple_home", {}), ctx)
    return None


@HOMES.register("none")
def _none(options: Mapping[str, Any], ctx: AdapterContext) -> None:
    return None
