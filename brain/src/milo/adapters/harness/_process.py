"""Run a harness CLI with stdin closed and a hard timeout, reading its stdout line by line."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from pathlib import Path

from milo.core.types import HarnessError

log = logging.getLogger(__name__)

STDOUT_LIMIT = 16 * 1024 * 1024  # one JSON event can carry a whole command's output


async def run(cmd: list[str], *, cwd: Path, timeout_s: float, on_line: Callable[[str], None] | None = None,
              env: Mapping[str, str] | None = None) -> tuple[int, str, str]:
    """Return (exit code, stdout, stderr). Raises HarnessError on timeout or if the binary won't start.

    `on_line` gets each stdout line as it arrives. An exception in it is logged, never raised. `env` replaces
    the environment; None inherits it.
    """
    try:
        # stdin must be closed: `codex exec` waits for piped stdin otherwise and hangs.
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL, limit=STDOUT_LIMIT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        raise HarnessError(f"could not start {Path(cmd[0]).name}: {e}", transient=False) from None
    out: list[str] = []

    async def read_stdout() -> None:
        while raw := await proc.stdout.readline():
            line = raw.decode(errors="replace")
            out.append(line)
            if on_line is not None:
                try:
                    on_line(line)
                except Exception:
                    log.exception("progress callback failed")

    async def finish() -> bytes:
        _, err = await asyncio.gather(read_stdout(), proc.stderr.read())
        await proc.wait()
        return err

    try:
        err = await asyncio.wait_for(finish(), timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise HarnessError(f"{Path(cmd[0]).name} timed out after {timeout_s:.0f}s", transient=True) from None
    except ValueError:  # a line over STDOUT_LIMIT
        proc.kill()
        await proc.wait()
        raise HarnessError(f"{Path(cmd[0]).name} printed a line too long to read", transient=True) from None
    return proc.returncode or 0, "".join(out), err.decode(errors="replace")


def last_line(err: str, code: int) -> str:
    """The most useful bit of a failed CLI's stderr: its last line."""
    return (err.strip().splitlines() or [f"exit code {code}"])[-1]
