"""Handle-relative POSIX worker cleanup; kept outside the platform-neutral core."""
from __future__ import annotations
import logging
import os
import stat
from pathlib import Path
log = logging.getLogger("milo.control")

def clear_steering(workdir: Path, names: tuple[str, ...]) -> None:
    """Remove what a helper could have left in its folder to steer the next one (STEERING), at any depth and
    in any case (APFS opens claude.md as CLAUDE.md). Raises OSError if one is still there.

    Another helper may be working in the folder meanwhile, so nothing here goes by path: every folder is
    opened relative to the one above it without following a link, and changed and emptied through that
    handle. A folder swapped for a link halfway is never entered, so nothing outside `workdir` is touched.
    A folder the helper locked gets its owner's permissions back."""
    left: list[str] = []
    root = os.open(workdir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _sweep(root, "", left, names=frozenset(name.casefold() for name in names))
    finally:
        os.close(root)
    if left:
        raise OSError(f"{', '.join(left)} in {workdir} can't be removed")


_FOLDER = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


MAX_DEPTH = 32
"""Folders deeper than this in the worker's folder aren't looked through: no helper runs until they're gone."""


def _sweep(folder: int, where: str, left: list[str], depth: int = 0, *, names: frozenset[str]) -> None:
    """Remove the STEERING entries in the open `folder` (`where` below the work folder) and below it. Whatever
    can't be checked counts as still there."""
    try:
        entries = [(e.name, e.is_dir(follow_symlinks=False)) for e in os.scandir(folder)]
    except OSError:
        left.append(where or ".")
        return
    for name, is_folder in entries:
        rel = f"{where}{name}"
        if name.casefold() in names:
            try:
                if is_folder:
                    _delete(folder, name)
                else:
                    os.unlink(name, dir_fd=folder)  # a link is removed itself
            except OSError as e:
                if not isinstance(e, FileNotFoundError):
                    log.warning("could not remove %s from the worker's folder: %s", rel, e)
            if _exists(folder, name):
                left.append(rel)
            else:
                log.warning("removed %s a helper left in its folder", rel)
        elif is_folder:
            if depth >= MAX_DEPTH:
                left.append(rel + " (too deep to look through)")
                continue
            child = _open_folder(folder, name)
            if child is None:
                if _is_folder(folder, name):
                    left.append(rel)  # a real folder that can't be opened: can't tell what's inside
                continue  # gone, or a link by now: links aren't followed
            try:
                _sweep(child, rel + "/", left, depth + 1, names=names)
            finally:
                os.close(child)


def _exists(folder: int, name: str) -> bool:
    """Only "not found" counts as gone: a name that can't be looked at may well still be there."""
    try:
        os.stat(name, dir_fd=folder, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _is_folder(folder: int, name: str) -> bool:
    try:
        return stat.S_ISDIR(os.stat(name, dir_fd=folder, follow_symlinks=False).st_mode)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _open_folder(parent: int, name: str) -> int | None:
    """`name` in `parent`, opened without following a link, after giving it its owner's permissions."""
    try:
        os.chmod(name, 0o700, dir_fd=parent, follow_symlinks=False)
    except (OSError, NotImplementedError, ValueError):
        # Some Linux Python builds cannot combine dir_fd with no-follow chmod.
        # O_PATH pins even an unreadable directory; its proc-fd path names that
        # exact inode, so changing its mode cannot be redirected by a rename.
        if hasattr(os, "O_PATH"):
            pinned = None
            try:
                pinned = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                if stat.S_ISDIR(os.fstat(pinned).st_mode):
                    os.chmod(f"/proc/self/fd/{pinned}", 0o700)
            except OSError:
                pass
            finally:
                if pinned is not None:
                    os.close(pinned)
    try:
        return os.open(name, _FOLDER, dir_fd=parent)
    except OSError:
        return None


def _delete(parent: int, name: str) -> None:
    """Delete the folder `name` in `parent` and everything in it, through handles only."""
    child = _open_folder(parent, name)
    if child is None:
        os.unlink(name, dir_fd=parent)  # a link swapped in for the folder; raises if it's something else
        return
    try:
        for entry in list(os.scandir(child)):
            try:
                if entry.is_dir(follow_symlinks=False):
                    _delete(child, entry.name)
                else:
                    os.unlink(entry.name, dir_fd=child)
            except FileNotFoundError:
                continue  # someone else removed it meanwhile; the rmdir below says if anything is left
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=parent)
