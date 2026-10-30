"""Which files Milo may send to the owner's phone (ADR 0015). Sending is a `share`: Approvals asks first."""

from __future__ import annotations

from pathlib import Path

MAX_FILE_MB = 45.0

# Folders under the home folder nothing is ever sent from: keys, passwords, Milo's own and the agents' state.
PRIVATE = (".ssh", ".gnupg", ".aws", ".config", ".netrc", ".codex", ".claude", ".docker", ".kube",
           "Library/Keychains", "Library/Cookies", "Library/Messages", "Library/Mail",
           "Library/Application Support/com.apple.TCC", "Library/Group Containers")


class NotShareable(Exception):
    """Plain words for the helper: why this file can't be sent."""


def shareable(text: str, *, home: Path, milo: Path, max_mb: float = MAX_FILE_MB) -> Path:
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
    except (OSError, RuntimeError):
        raise NotShareable(f"There's no file at {text.strip()}.") from None
    if not path.is_file():
        raise NotShareable(f"{path.name} is a folder. Send one file, or zip the folder first.")
    home, milo = home.resolve(), milo.resolve()
    if any(path.is_relative_to(home / p) for p in PRIVATE) or path.name.startswith(".env"):
        raise NotShareable(f"{path.name} is in a private place (keys, passwords or app data). Milo never sends "
                           f"files from there.")
    if path.is_relative_to(milo):
        inside = path.relative_to(milo).parts
        if not inside or inside[0] in ("config.toml", "state", "logs", "secrets", "run", "memory", ".codex") \
                or inside[0].startswith("."):
            raise NotShareable(f"{path.name} is part of Milo's own settings or memory. Milo doesn't send those.")
    size = path.stat().st_size
    if size > max_mb * 1024 * 1024:
        raise NotShareable(f"{path.name} is {size / 1024 / 1024:.0f} MB, more than the {max_mb:.0f} MB Milo may "
                           f"send by message.")
    return path


def size_text(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} KB"
    return f"{size / 1024 / 1024:.1f} MB"
