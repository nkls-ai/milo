"""Secret files: API keys and bot tokens, each alone in a file under ~/Milo/secrets (never in config.toml).

One reader for all of them, so every key gets the same checks. A secret is only read from a plain file the
user owns, in a folder the user owns. If others on the Mac could read the file (mode not 0600) or list the
folder (not 0700), Milo tightens both itself and says so in the log: the key is the user's own, so there is
nothing to ask. A link, a folder, or a file of another user is refused, since Milo can't tell who controls it.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

log = logging.getLogger("milo.secrets")

FILE_MODE = 0o600
DIR_MODE = 0o700


class SecretError(Exception):
    """The secret can't be read safely, or isn't there. The message is plain words with the fix."""


def read_secret(path: Path, what: str, *, missing: str = "") -> str:
    """The stripped contents of the secret file `path`. `what` names it for the user ("The ElevenLabs key");
    `missing` replaces the message for a file that isn't there. Raises SecretError."""
    path = path.expanduser()
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise SecretError(missing or f"{what} is missing: put it alone in {path}.") from None
    except OSError as e:
        raise SecretError(f"Can't read {what.lower()} file {path}: {e.strerror}.") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise SecretError(f"{what} file {path} must be a plain file, not a link or a folder.")
    if info.st_uid != os.getuid():
        raise SecretError(f"{what} file {path} belongs to another user.")
    _private(path.parent, DIR_MODE, what)
    _private(path, FILE_MODE, what, info.st_mode)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as e:
        raise SecretError(f"Can't read {what.lower()} file {path}: {getattr(e, 'strerror', None) or e}.") from None
    if not text:
        raise SecretError(f"{what} file {path} is empty.")
    return text


def _private(path: Path, mode: int, what: str, current: int | None = None) -> None:
    """Make `path` (the user's own) readable by the user alone. Refuses a folder of another user."""
    if current is None:
        try:
            info = path.stat()
        except OSError as e:
            raise SecretError(f"Can't check the folder {path}: {e.strerror}.") from None
        if info.st_uid != os.getuid():
            raise SecretError(f"The folder {path} that holds {what.lower()} belongs to another user.")
        current = info.st_mode
    if current & 0o077 == 0:
        return
    try:
        os.chmod(path, mode)
    except OSError as e:
        raise SecretError(f"Others on this Mac can read {what.lower()} in {path}, and Milo couldn't fix it "
                          f"({e.strerror}). Run: chmod {mode:o} {path}") from None
    log.warning("%s: others on this Mac could read %s; made it %o", what, path, mode)
