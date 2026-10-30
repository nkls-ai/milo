"""Milo's control files: what decides his rules, his memory and his approvals (ADR 0020).

Helpers never write them. The worker runs in a folder of its own (`work/`), so its sandbox can't reach them,
and every tool that runs outside that sandbox (the files tools, scripts in Milo.app) checks a path against
`Protected` before it touches it. They change only through the Settings window, Milo's own tags and tools with
the user's yes, or the user's own editor.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

CONTROL_FILES = ("config.toml", "persona.md", "AGENTS.md", "CLAUDE.md", "reminders.md")
"""Files directly in the workspace."""
CONTROL_FOLDERS = ("routines", "memory", "secrets", "state", "run", ".codex", ".claude")
"""Folders in the workspace, with everything below them. state/ holds the paired phone, the routines the user
approved and the worker's own settings; run/ the sockets; .codex and .claude the worker CLIs' homes."""

WORK_FOLDER = "work"
"""The one folder in the workspace the worker may write: its scratch space and routine drafts."""

STEERING = ("AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md", ".codex", ".claude", ".mcp.json",
            ".agents")
"""What Codex or Claude Code would read from their working folder (or a folder below, where Claude Code reads
CLAUDE.md when it opens files there) as instructions, settings or tools. The worker's folder is its own to
write, so a helper could leave these for the next one: they are removed at any depth before every run
(`clear_steering`), Claude Code is denied writing them, and Codex reads no AGENTS.md but its home's."""
STEERING_FOLDERS = (".codex", ".claude", ".agents")

log = logging.getLogger("milo.control")


@dataclass(frozen=True)
class Protected:
    """The control paths of the workspace `home`. Names compare without case, like APFS."""

    home: Path

    @property
    def paths(self) -> tuple[Path, ...]:
        return (*(self.home / name for name in CONTROL_FILES), *(self.home / name for name in CONTROL_FOLDERS))

    def covers(self, path: Path | str) -> bool:
        """Whether `path` is a control file or inside a control folder. Links are resolved first, so a link
        in the worker's folder can't point a write at config.toml."""
        target = _fold(_resolved(Path(path).expanduser()))
        for control in self.paths:
            folded = _fold(_resolved(control))
            if target == folded or target.startswith(folded + "/"):
                return True
        return False

    def mentioned_in(self, text: str) -> list[Path]:
        """Control paths a script names, by full path or by ~/ path, like "~/Milo/config.toml"."""
        homes = {str(_resolved(self.home)), str(self.home)}
        try:
            homes.add("~/" + str(self.home.relative_to(Path.home())))
        except ValueError:
            pass
        found = []
        folded = text.casefold()
        for control in self.paths:
            rel = control.name
            for home in homes:
                needle = f"{home}/{rel}".casefold()
                if re.search(re.escape(needle) + r"(?![\w.-])", folded):
                    found.append(control)
                    break
        return found

    def resolved(self) -> list[str]:
        """Every control path, links resolved, for an OS sandbox's write deny list."""
        return [str(_resolved(control)) for control in self.paths]

    def deny_rules(self) -> list[str]:
        """Claude Code permission rules that keep its file tools off every control path."""
        rules = []
        for control in self.paths:
            target = f"/{_resolved(control)}" + ("/**" if control.name in CONTROL_FOLDERS else "")
            rules += [f"Edit({target})", f"Write({target})"]
        secrets = f"/{_resolved(self.home / 'secrets')}/**"
        return [*rules, f"Read({secrets})"]


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _fold(path: Path) -> str:
    return str(path).casefold().rstrip("/")


def clear_steering(workdir: Path) -> None:
    """Remove what a helper could have left in its folder to steer the next one (STEERING), at any depth and
    in any case (APFS opens claude.md as CLAUDE.md). Raises OSError if one is still there.

    Another helper may be working in the folder meanwhile, so nothing here goes by path: every folder is
    opened relative to the one above it without following a link, and changed and emptied through that
    handle. A folder swapped for a link halfway is never entered, so nothing outside `workdir` is touched.
    A folder the helper locked gets its owner's permissions back."""
    left: list[str] = []
    root = os.open(workdir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _sweep(root, "", left)
    finally:
        os.close(root)
    if left:
        raise OSError(f"{', '.join(left)} in {workdir} can't be removed")


_STEERING_FOLDED = frozenset(name.casefold() for name in STEERING)
_FOLDER = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _sweep(folder: int, where: str, left: list[str]) -> None:
    """Remove the STEERING entries in the open `folder` (`where` below the work folder) and below it."""
    try:
        entries = [(e.name, e.is_dir(follow_symlinks=False)) for e in os.scandir(folder)]
    except OSError:
        left.append(where or ".")
        return
    for name, is_folder in entries:
        rel = f"{where}{name}"
        if name.casefold() in _STEERING_FOLDED:
            try:
                if is_folder:
                    _delete(folder, name)
                else:
                    os.unlink(name, dir_fd=folder)  # a link is removed itself
                log.warning("removed %s a helper left in its folder", rel)
            except FileNotFoundError:
                pass
            except OSError as e:
                log.warning("could not remove %s from the worker's folder: %s", rel, e)
                left.append(rel)
        elif is_folder:
            child = _open_folder(folder, name)
            if child is None:
                continue  # gone, or a link by now: links aren't followed
            try:
                _sweep(child, rel + "/", left)
            finally:
                os.close(child)


def _open_folder(parent: int, name: str) -> int | None:
    """`name` in `parent`, opened without following a link, after giving it its owner's permissions."""
    try:
        os.chmod(name, 0o700, dir_fd=parent, follow_symlinks=False)
    except OSError:
        pass
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
            if entry.is_dir(follow_symlinks=False):
                _delete(child, entry.name)
            else:
                os.unlink(entry.name, dir_fd=child)
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=parent)
