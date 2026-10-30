"""While the owner is away and Milo can be reached by message, config.toml can't change (ADR 0015).

A helper started from the phone works in ~/Milo and could edit config.toml: switch connections back on,
loosen the approval levels, or point messages at another bot. Approval levels are only read at start, but
the next restart would pick the change up. So while the guard is on, a changed config.toml is put back the
way it was when the guard came on, and the Mac says so. At the Mac (not away) nothing is guarded.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("milo.settings_guard")

PUT_BACK = "Milo's settings changed while you were away, so I put them back. Change them at the Mac."


class SettingsGuard:
    def __init__(self, path: Path, on_restore: Callable[[str], None] = lambda text: None):
        self._path = path
        self._on_restore = on_restore
        self._kept: bytes | None = None

    @property
    def on(self) -> bool:
        return self._kept is not None

    def check(self, guarding: bool) -> bool:
        """Turn the guard on or off, and put config.toml back if it changed while on. True if it did."""
        if not guarding:
            self._kept = None
            return False
        try:
            current = self._path.read_bytes()
        except OSError:
            current = None
        if self._kept is None:
            self._kept = current if current is not None else b""
            return False
        if current == self._kept:
            return False
        log.warning("config.toml changed while the owner was away; putting it back")
        tmp = self._path.with_name(self._path.name + ".guard")
        try:
            mode = self._path.stat().st_mode & 0o777 if self._path.exists() else 0o600
            tmp.write_bytes(self._kept)
            os.chmod(tmp, mode)
            os.replace(tmp, self._path)
        except OSError:
            log.exception("could not put config.toml back")
            return False
        self._on_restore(PUT_BACK)
        return True
