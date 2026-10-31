"""Runs an install the worker asked for (install_package), outside the helper's sandbox.

The command comes from `core/packages.py`: a known package manager, its plain install command and a checked package
name, as an argv list (no shell). It runs as the user, never with sudo, in an empty folder so a name can't point at a
file, with stdin closed so nothing waits for a password. The brain was started by the app, maybe with a bare PATH,
so the managers are also looked for where they usually live (`search_dirs`, nvm's and the user's own bin folders).

Whether it may run without a question is decided before this (ToolRequests, Approvals); this only runs it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from milo import system
from milo.core.packages import Install

log = logging.getLogger("milo.installs")

WAIT_S = 120.0
"""How long the worker's tool call waits for the install. A helper's turn ends after 180 s by default, so a longer
install goes on alone and the worker hears that it is still running."""
OUTPUT_TAIL = 1500
"""The end of the manager's output that goes back to the worker: enough for the error, never a whole log."""
QUIET = {"NONINTERACTIVE": "1", "HOMEBREW_NO_ENV_HINTS": "1", "npm_config_yes": "true", "npm_config_fund": "false",
         "npm_config_update_notifier": "false"}
"""Nothing may wait for an answer: stdin is closed, and these keep the managers from asking or advertising."""


class Installer:
    def __init__(self, *, search_dirs: Sequence[str | Path] = (), home: Path | None = None,
                 env: Mapping[str, str] | None = None, wait_s: float = WAIT_S):
        self._home = home or Path.home()
        self._env = dict(os.environ if env is None else env)
        self._dirs = [Path(d).expanduser() for d in search_dirs]
        self._wait_s = wait_s
        self._one_at_a_time = asyncio.Lock()
        """Two managers at once fight over their locks (Homebrew's, npm's global folder)."""
        self._running: set[asyncio.Task] = set()

    def path(self) -> list[str]:
        """Where the package managers are looked for: the brain's PATH first, then the usual places."""
        dirs = [d for d in self._env.get("PATH", "").split(os.pathsep) if d]
        nvm = self._home / ".nvm" / "versions" / "node"
        nodes = sorted(nvm.glob("*/bin"), key=lambda p: _version(p.parent.name), reverse=True) if nvm.is_dir() else []
        extra = [*self._dirs, *nodes, self._home / ".volta" / "bin", self._home / ".local" / "bin",
                 self._home / ".cargo" / "bin"]
        for d in extra:
            if str(d) not in dirs and d.is_dir():
                dirs.append(str(d))
        return dirs

    def find(self, program: str) -> str | None:
        return shutil.which(program, path=os.pathsep.join(self.path()))

    async def run(self, install: Install) -> dict:
        """{"installed": bool, "output": the end of what the manager said} or {"running": True, ...} if it takes
        longer than the worker can wait. Raises ValueError when the manager isn't on this computer."""
        binary = self.find(install.program)
        if binary is None:
            raise ValueError(f"{install.label} isn't installed on this computer ({install.program} wasn't found), so "
                             f"it can't install {install.package}. Try another manager, or tell the user.")
        # The manager's own folder goes first, so `#!/usr/bin/env node` finds the node that belongs to this npm.
        path = os.pathsep.join([str(Path(binary).parent), *self.path()])
        env = {**self._env, **QUIET, "PATH": path}
        # Held until the install ends, even one that outlasts the worker's wait.
        await self._one_at_a_time.acquire()
        folder = tempfile.mkdtemp(prefix="milo-install-")
        try:
            log.info("installing %s", install)
            # A session of its own: no terminal, so a sudo somewhere inside can't ask for a password.
            proc = await asyncio.create_subprocess_exec(
                binary, *install.argv[1:], cwd=folder, env=env, stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **system.isolated_process())
        except OSError as e:
            shutil.rmtree(folder, ignore_errors=True)
            self._one_at_a_time.release()
            raise ValueError(f"could not start {install.program}: {e}") from None
        finish = asyncio.ensure_future(self._finish(proc, install, folder))
        self._running.add(finish)
        finish.add_done_callback(self._running.discard)
        finish.add_done_callback(lambda _: self._one_at_a_time.release())
        try:
            code, output = await asyncio.wait_for(asyncio.shield(finish), self._wait_s)
        except TimeoutError:
            return {"running": True, "command": str(install),
                    "note": f"{install.package} is still installing and will finish on its own. Check in a minute "
                            f"or two whether it's there; don't start it again."}
        return {"installed": code == 0, "command": str(install), "exit_code": code, "output": _tail(output)}

    async def _finish(self, proc: asyncio.subprocess.Process, install: Install, folder: str) -> tuple[int, str]:
        try:
            out, _ = await proc.communicate()
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        code = proc.returncode if proc.returncode is not None else -1
        log.info("installing %s ended with %d", install, code)
        return code, out.decode(errors="replace")


def _version(name: str) -> tuple[int, ...]:
    """'v22.23.3' -> (22, 23, 3), for picking the newest node nvm has."""
    return tuple(int(n) for n in re.findall(r"\d+", name)[:3])


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= OUTPUT_TAIL else "…" + text[-OUTPUT_TAIL:]
