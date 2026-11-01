"""While the owner is away and Milo can be reached by message, Milo's settings can't change (ADR 0017).

Helpers can't write these files (ADR 0020), but one driving the Mac's apps could still type into them in an
editor. What a helper started from the phone could change decides Milo's safety: config.toml
(switch connections back on, loosen the approval levels), state/messages.json (who the paired phone is)
or secrets/ (swap the bot token for someone else's bot). Most of these are only read at start, but the
next restart would pick a change up. So while the guard is on, every guarded file is put back the way it
was when the guard came on, and the Mac says so. Milo's own saves (`refresh`) are kept. At the Mac (not
away) nothing is guarded.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from milo import system

log = logging.getLogger("milo.settings_guard")

PUT_BACK = "Milo's settings changed while you were away, so I put them back. Change them at the Mac."

Snapshot = dict[Path, tuple[bytes, int] | None]
"""Each guarded file's bytes and permission bits, None if it didn't exist."""


class SettingsGuard:
    """`files` are guarded one by one; every file directly inside `folders` is too, including new ones."""

    def __init__(self, files: Sequence[Path], folders: Sequence[Path] = (),
                 on_restore: Callable[[str], None] = lambda text: None):
        self._files = list(files)
        self._folders = list(folders)
        self._on_restore = on_restore
        self._kept: Snapshot | None = None

    @property
    def on(self) -> bool:
        return self._kept is not None

    def check(self, guarding: bool) -> bool:
        """Turn the guard on or off, and put files back if they changed while on. True if any was."""
        if not guarding:
            self._kept = None
            return False
        now = self._snapshot()
        if self._kept is None:
            self._kept = now
            return False
        changed = [p for p in self._kept.keys() | now.keys() if self._kept.get(p) != now.get(p)]
        if not changed:
            return False
        log.warning("%d of Milo's settings files changed while the owner was away; putting them back", len(changed))
        for path in changed:
            try:
                _restore(path, self._kept.get(path))
            except OSError:
                log.exception("could not put %s back", path.name)
        self._on_restore(PUT_BACK)
        return True

    def refresh(self, path: Path | None) -> None:
        """Milo itself saved `path`: keep the new version."""
        if self._kept is not None and path is not None:
            self._kept[path] = _read(path)

    def _snapshot(self) -> Snapshot:
        paths = set(self._files)
        for folder in self._folders:
            try:
                paths.update(p for p in folder.iterdir() if not p.is_dir() or p.is_symlink())
            except OSError:
                pass
        return {p: _read(p) for p in paths}


def _read(path: Path) -> tuple[bytes, int] | None:
    try:
        if path.is_symlink():
            return (b"link:" + os.readlink(path).encode(), 0)
        return path.read_bytes(), path.stat().st_mode & 0o777
    except OSError:
        return None


def _restore(path: Path, kept: tuple[bytes, int] | None) -> None:
    if kept is None:
        path.unlink(missing_ok=True)
        return
    data, mode = kept
    if path.is_symlink():
        path.unlink()
    tmp = path.with_name(path.name + ".guard")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        system.make_private(f.fileno(), mode or 0o600)
        f.write(data)
    system.replace_file(tmp, path)
