"""Secret files: API keys and bot tokens, each alone in a file under ~/Milo/secrets (never in config.toml).

One reader for all of them, so every key gets the same checks. A secret is only read from a plain file the
user owns, in a folder the user owns. If others on the computer could read the file (mode not 0600) or list the
folder (not 0700), Milo tightens both itself and says so in the log: the key is the user's own, so there is
nothing to ask. A link, a folder, or a file of another user is refused, since Milo can't tell who controls it.
"""

from __future__ import annotations

import errno
import logging
import os
import stat
from pathlib import Path

from milo import system

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
        fd = system.open_no_follow(path)
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
        if not system.owned_by_me(fd):
            raise SecretError(f"{what} file {path} belongs to another user.")
        if system.open_to_others(fd):
            try:
                system.make_private(fd, FILE_MODE)
            except OSError as e:
                raise SecretError(f"Others on this computer can read {what.lower()} in {path}, and Milo couldn't fix "
                                  f"it ({e.strerror}). Run: chmod {FILE_MODE:o} {path}") from None
            log.warning("%s: others on this computer could read %s; made it %o", what, path, FILE_MODE)
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
    if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_reparse_tag", 0):
        raise SecretError(f"The folder {folder} that holds {what.lower()} must be a real folder, not a link.")
    if not system.owned_by_me(folder):
        raise SecretError(f"The folder {folder} that holds {what.lower()} belongs to another user.")
    if system.open_to_others(folder):
        try:
            system.make_private(folder, DIR_MODE)
        except OSError as e:
            raise SecretError(f"Others on this computer can list {folder}, and Milo couldn't fix it ({e.strerror}). "
                              f"Run: chmod {DIR_MODE:o} {folder}") from None
        log.warning("%s: others on this computer could list %s; made it %o", what, folder, DIR_MODE)


def write_secret(path: Path, text: str, what: str) -> None:
    """Puts `text` alone in the secret file `path`, private to the user, replacing what was there. For a key the
    user pasted into Setup; the text is never logged. Raises SecretError, leaving any old file as it was."""
    text = text.strip()
    if not text or "\n" in text or "\r" in text or "\0" in text:
        raise SecretError(f"{what} must be a single line.")
    path = path.expanduser()
    folder = path.parent
    try:
        folder.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        _private_folder(folder, what)
        partial = folder / f".{path.name}.new"
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), FILE_MODE)
        try:
            os.write(fd, (text + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        system.make_private(partial, FILE_MODE)
        os.replace(partial, path)
    except OSError as e:
        raise SecretError(f"Couldn't save {what.lower()} in {folder}: {e.strerror}.") from None
    log.info("%s saved in %s", what, path)
