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
import stat
from dataclasses import dataclass
from pathlib import Path

CONTROL_FILES = ("config.toml", "persona.md", "AGENTS.md", "CLAUDE.md", "reminders.md", "dictionary.md")
"""Files directly in the workspace. dictionary.md changes what the user's dictation says before it is pasted."""
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
        homes = {_resolved(self.home).as_posix(), self.home.as_posix()}
        try:
            homes.add("~/" + self.home.relative_to(Path.home()).as_posix())
        except ValueError:
            pass
        found = []
        folded = text.replace("\\", "/").casefold()
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
            target = f"/{_resolved(control).as_posix()}" + ("/**" if control.name in CONTROL_FOLDERS else "")
            rules += [f"Edit({target})", f"Write({target})"]
        secrets = f"/{_resolved(self.home / 'secrets').as_posix()}/**"
        return [*rules, f"Read({secrets})"]


def _resolved(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _fold(path: Path) -> str:
    return path.as_posix().casefold().rstrip("/")


def clear_steering(workdir: Path) -> None:
    """Remove helper-written steering without following filesystem links."""
    from milo import system

    system.clear_steering(workdir, STEERING)
