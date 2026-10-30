"""Which files Milo may send to the owner's phone (ADR 0017). Sending is a `share`: Approvals asks first.

The check runs twice: when the helper asks (for the question) and again right before sending, on the one
open file whose bytes go out. A file swapped or replaced by a link while the question waited is refused.
Paths are compared case-insensitively, as the Mac's disk treats them ("~/.SSH" is "~/.ssh").
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_MB = 45.0

# Folders under the home folder nothing is ever sent from: keys, passwords, Milo's own and the agents' state.
PRIVATE = (".ssh", ".gnupg", ".aws", ".config", ".netrc", ".codex", ".claude", ".docker", ".kube",
           "Library/Keychains", "Library/Cookies", "Library/Messages", "Library/Mail",
           "Library/Application Support/com.apple.TCC", "Library/Group Containers")
# In Milo's own folder: everything but what helpers made there.
MILO_PRIVATE = ("config.toml", "state", "logs", "secrets", "run", "memory", "persona.md", "reminders.md",
                "agents.md", "claude.md")


class NotShareable(Exception):
    """Plain words for the helper: why this file can't be sent."""


@dataclass(frozen=True)
class Outgoing:
    """A file that passed the check, and which file it was on disk (device, inode, size, change time)."""

    path: Path
    size: int
    identity: tuple[int, int, int, int]

    @property
    def name(self) -> str:
        return self.path.name


def shareable(text: str, *, home: Path, milo: Path, max_mb: float = MAX_FILE_MB) -> Outgoing:
    """The file `text` names, resolved, if Milo may send it. Raises NotShareable.

    Links are followed first, so a link can't smuggle out a file from a private folder. From Milo's own
    folder only what the helpers made in it counts: never config.toml, state, logs, secrets or memory.
    """
    if not text.strip():
        raise NotShareable("Say which file to send.")
    path = Path(text.strip()).expanduser()
    if not path.is_absolute():
        path = milo / path
    try:
        path = path.resolve(strict=True)
        info = path.stat()
    except (OSError, RuntimeError):
        raise NotShareable(f"There's no file at {text.strip()}.") from None
    if not stat.S_ISREG(info.st_mode):
        raise NotShareable(f"{path.name} isn't a file. Send one file, or zip a folder first.")
    _allowed(path, home.resolve(), milo.resolve())
    if info.st_size > max_mb * 1024 * 1024:
        raise NotShareable(f"{path.name} is {info.st_size / 1024 / 1024:.0f} MB, more than the {max_mb:.0f} MB "
                           f"Milo may send by message.")
    return Outgoing(path, info.st_size, _identity(info))


def read(outgoing: Outgoing, *, home: Path, milo: Path, max_mb: float = MAX_FILE_MB) -> bytes:
    """The bytes of a file shareable() passed, if it is still the same file in the same place. Opened once,
    without following a link, so what is checked is what is sent. Raises NotShareable."""
    again = shareable(str(outgoing.path), home=home, milo=milo, max_mb=max_mb)
    if again.path != outgoing.path or again.identity != outgoing.identity:
        raise NotShareable(f"{outgoing.name} changed while I asked you, so I didn't send it. Ask me again.")
    try:
        fd = os.open(outgoing.path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise NotShareable(f"{outgoing.name} can't be opened any more.") from None
    with os.fdopen(fd, "rb") as f:
        if _identity(os.fstat(f.fileno())) != outgoing.identity:
            raise NotShareable(f"{outgoing.name} changed while I asked you, so I didn't send it. Ask me again.")
        data = f.read(outgoing.size + 1)
    if len(data) != outgoing.size:
        raise NotShareable(f"{outgoing.name} changed while I asked you, so I didn't send it. Ask me again.")
    return data


def _allowed(path: Path, home: Path, milo: Path) -> None:
    folded = _fold(path)
    if any(_under(folded, _fold(home / p)) for p in PRIVATE) or path.name.casefold().startswith(".env"):
        raise NotShareable(f"{path.name} is in a private place (keys, passwords or app data). Milo never sends "
                           f"files from there.")
    milo_folded = _fold(milo)
    if _under(folded, milo_folded):
        inside = folded[len(milo_folded):]
        if not inside or inside[0] in MILO_PRIVATE or inside[0].startswith("."):
            raise NotShareable(f"{path.name} is part of Milo's own settings or memory. Milo doesn't send those.")


def _fold(path: Path) -> tuple[str, ...]:
    return tuple(part.casefold() for part in path.parts)


def _under(path: tuple[str, ...], folder: tuple[str, ...]) -> bool:
    return path[:len(folder)] == folder


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def size_text(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} KB"
    return f"{size / 1024 / 1024:.1f} MB"
