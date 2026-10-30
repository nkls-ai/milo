"""Find a harness CLI. The app is launched from Finder, so PATH is often missing the usual dirs."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from milo.core.registry import ConfigError


def find_binary(configured: str, name: str, fallbacks: Sequence[Path] = (), *, section: str) -> str:
    """Configured path, then PATH, then ~/.local/bin and /opt/homebrew/bin, then `fallbacks`."""
    if configured:
        return str(Path(configured).expanduser())
    found = shutil.which(name)
    if found:
        return found
    for path in (Path.home() / ".local/bin" / name, Path("/opt/homebrew/bin") / name, *fallbacks):
        if path.exists():
            return str(path)
    raise ConfigError(f"could not find `{name}`; set `binary` in [{section}]")
