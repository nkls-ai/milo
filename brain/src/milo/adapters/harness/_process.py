"""Run a harness CLI with stdin closed and a hard timeout, reading its stdout line by line."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from milo.core.types import HarnessError

log = logging.getLogger(__name__)

STDOUT_LIMIT = 16 * 1024 * 1024  # one JSON event can carry a whole command's output
# After the answer is in, how long a CLI may keep tidying up (codex takes 4-6 s) before it is killed.
LINGER_S = 30.0
# How long run() waits for a CLI to exit after its answer before it leaves the CLI to finish alone.
EXIT_WAIT_S = 0.3
# How long a stopped CLI gets to end its tool servers and save its session before it is killed.
STOP_GRACE_S = 2.0

_lingering: set[asyncio.Task] = set()


async def run(cmd: list[str], *, cwd: Path, timeout_s: float,
              on_line: Callable[[str], None] | None = None,
              done: Callable[[str], bool] | None = None,
              env: Mapping[str, str] | None = None) -> tuple[int, str, str]:
    """Return (exit code, stdout, stderr). Raises HarnessError on timeout or if the binary won't start.

    `on_line` gets each stdout line as it arrives. An exception in it is logged, never raised. `done` tells
    the line that carries the answer: then run() returns at once (exit code 0, stderr so far) and leaves the
    CLI to finish on its own, so nobody waits for it to shut down. `env` replaces the environment; None
    inherits it.

    The CLI runs in its own process group. A timeout, or cancelling the call, ends it and every process it
    started, including those in groups of their own (codex starts each shell command that way).
    """
    try:
        # stdin must be closed: `codex exec` waits for piped stdin otherwise and hangs.
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd, env=env, stdin=asyncio.subprocess.DEVNULL, limit=STDOUT_LIMIT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True,
        )
    except OSError as e:
        raise HarnessError(f"could not start {Path(cmd[0]).name}: {e}", transient=False) from None
    out: list[str] = []
    err: list[bytes] = []

    async def read_stdout() -> bool:
        """True when the answer line came, False at the end of the output."""
        while raw := await proc.stdout.readline():
            line = raw.decode(errors="replace")
            out.append(line)
            if on_line is not None:
                try:
                    on_line(line)
                except Exception:
                    log.exception("progress callback failed")
            if done is not None and done(line):
                return True
        return False

    async def read_stderr() -> None:
        while chunk := await proc.stderr.read(65536):
            err.append(chunk)

    stderr = asyncio.create_task(read_stderr())
    try:
        answered = await asyncio.wait_for(read_stdout(), timeout_s)
        if answered:
            try:  # most CLIs end right after their answer; give them a moment before leaving them to it
                await asyncio.wait_for(asyncio.shield(proc.wait()), EXIT_WAIT_S)
            except TimeoutError:
                pass
            if proc.returncode is None:
                _linger(proc, stderr)
            else:
                await asyncio.wait_for(asyncio.gather(stderr, read_stdout()), 1.0)
        else:
            await asyncio.wait_for(asyncio.gather(stderr, proc.wait()), max(1.0, timeout_s))
    except TimeoutError:
        await stop(proc)
        stderr.cancel()
        raise HarnessError(f"{Path(cmd[0]).name} timed out after {timeout_s:.0f}s", transient=True) from None
    except ValueError:  # a line over STDOUT_LIMIT
        await stop(proc)
        stderr.cancel()
        raise HarnessError(f"{Path(cmd[0]).name} printed a line too long to read", transient=True) from None
    except asyncio.CancelledError:
        # Stopped by Milo (the user said stop, or changed the task): end the CLI and all it started.
        await asyncio.shield(stop(proc))
        stderr.cancel()
        raise
    code = 0 if answered else proc.returncode or 0
    return code, "".join(out), b"".join(err).decode(errors="replace")


async def stop(proc: asyncio.subprocess.Process, grace_s: float = STOP_GRACE_S) -> None:
    """SIGTERM the CLI and everything it started, SIGKILL what is still there after `grace_s`.

    The process tree is read before the first signal: once the CLI is gone its children belong to launchd
    and can't be found from it any more.
    """
    if proc.returncode is not None:
        return
    tree = await asyncio.to_thread(descendants, proc.pid)  # ps takes tens of ms: not on the event loop
    _signal(proc.pid, [pid for pid, _ in tree], signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), grace_s)
    except TimeoutError:
        pass
    # Only those still the same processes: in the grace a pid that ended may have gone to someone else.
    _signal(proc.pid, await asyncio.to_thread(still_running, tree), signal.SIGKILL)
    try:
        # wait() also waits for the pipes, which a process that escaped the tree could hold open forever.
        await asyncio.wait_for(asyncio.shield(proc.wait()), grace_s)
    except TimeoutError:
        log.warning("%s was killed, but something it started still holds its output open", proc.pid)


def descendants(pid: int) -> list[tuple[int, str]]:
    """Every process below `pid`, children first, each with its start time. Empty if ps can't be read."""
    table = _processes()
    children: dict[int, list[int]] = {}
    for child, (parent, _) in table.items():
        children.setdefault(parent, []).append(child)
    found, todo = [], list(children.get(pid, []))
    while todo:
        child = todo.pop()
        found.append((child, table[child][1]))
        todo.extend(children.get(child, []))
    return found


def still_running(tree: list[tuple[int, str]]) -> list[int]:
    """The pids of `tree` that are still the processes they were: same pid, same start time."""
    table = _processes()
    return [pid for pid, started in tree if pid in table and table[pid][1] == started]


def _processes() -> dict[int, tuple[int, str]]:
    """pid -> (parent pid, start time) for every process. Empty if ps can't be read."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,lstart="], capture_output=True, text=True,
                             timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    table = {}
    for line in out.splitlines():
        parts = line.split(maxsplit=2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2].strip())
    return table


def _signal(root: int, tree: list[int], sig: int) -> None:
    """`sig` to the CLI's group and to each process it started, as a group when it leads one."""
    for pid in (root, *tree):
        try:
            os.killpg(pid, sig)  # fails for a process that leads no group
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass


def _linger(proc: asyncio.subprocess.Process, stderr: asyncio.Task) -> None:
    """Let a CLI that already answered exit by itself, draining its pipes, and kill it after LINGER_S."""

    async def drain() -> None:
        try:
            while await proc.stdout.readline():
                pass
        except (ValueError, OSError):
            pass

    async def wait() -> None:
        try:
            await asyncio.wait_for(asyncio.gather(drain(), stderr, proc.wait()), LINGER_S)
        except TimeoutError:
            log.info("%s still running %.0fs after its answer, stopping it", proc.pid, LINGER_S)
            await stop(proc)
            stderr.cancel()

    task = asyncio.create_task(wait())
    task.proc = proc
    _lingering.add(task)
    task.add_done_callback(_lingering.discard)


async def close_lingering() -> None:
    """Stop every CLI that answered but hasn't exited yet. On shutdown."""
    tasks = list(_lingering)
    await asyncio.gather(*(stop(t.proc, 0.5) for t in tasks), return_exceptions=True)
    await asyncio.gather(*tasks, return_exceptions=True)


def last_line(err: str, code: int) -> str:
    """The most useful bit of a failed CLI's stderr: its last line."""
    return (err.strip().splitlines() or [f"exit code {code}"])[-1]
