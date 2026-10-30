"""Secret files: API keys and bot tokens, each alone in a file under ~/Milo/secrets (never in config.toml).

One reader for all of them, so every key gets the same checks. A secret is only read from a plain file the
user owns, in a folder the user owns. If others on the Mac could read the file (mode not 0600) or list the
folder (not 0700), Milo tightens both itself and says so in the log: the key is the user's own, so there is
nothing to ask. A link, a folder, or a file of another user is refused, since Milo can't tell who controls it.
"""

from __future__ import annotations

import errno
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
    `missing` replaces the message for a file that isn't there. Raises SecretError.

    The folder is checked and tightened first; then the file is opened once without following a link, and
    every check, the chmod and the read go through that one handle, so it can't be swapped in between."""
    path = path.expanduser()
    _private_folder(path.parent, what)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise SecretError(missing or f"{what} is missing: put it alone in {path}.") from None
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise SecretError(f"{what} file {path} must be a plain file, not a link or a folder.") from None
        raise SecretError(f"Can't read {what.lower()} file {path}: {e.strerror}.") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise SecretError(f"{what} file {path} must be a plain file, not a link or a folder.")
        if info.st_uid != os.getuid():
            raise SecretError(f"{what} file {path} belongs to another user.")
        if info.st_mode & 0o077:
            try:
                os.fchmod(fd, FILE_MODE)
            except OSError as e:
                raise SecretError(f"Others on this Mac can read {what.lower()} in {path}, and Milo couldn't fix "
                                  f"it ({e.strerror}). Run: chmod {FILE_MODE:o} {path}") from None
            log.warning("%s: others on this Mac could read %s; made it %o", what, path, FILE_MODE)
        with os.fdopen(os.dup(fd), "rb") as f:
            raw = f.read()
    finally:
        os.close(fd)
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise SecretError(f"{what} file {path} isn't text.") from None
    if not text:
        raise SecretError(f"{what} file {path} is empty.")
    return text


def _private_folder(folder: Path, what: str) -> None:
    """The folder that holds a secret: the user's own, a real folder, listable by the user alone."""
    try:
        info = folder.lstat()
    except FileNotFoundError:
        return  # the file can't be there either: open() says it is missing
    except OSError as e:
        raise SecretError(f"Can't check the folder {folder}: {e.strerror}.") from None
    if not stat.S_ISDIR(info.st_mode):
        raise SecretError(f"The folder {folder} that holds {what.lower()} must be a real folder, not a link.")
    if info.st_uid != os.getuid():
        raise SecretError(f"The folder {folder} that holds {what.lower()} belongs to another user.")
    if info.st_mode & 0o077:
        try:
            os.chmod(folder, DIR_MODE, follow_symlinks=False)
        except OSError as e:
            raise SecretError(f"Others on this Mac can list {folder}, and Milo couldn't fix it ({e.strerror}). "
                              f"Run: chmod {DIR_MODE:o} {folder}") from None
        log.warning("%s: others on this Mac could list %s; made it %o", what, folder, DIR_MODE)
