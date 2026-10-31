"""The OS primitives on Windows: not written yet. Each function says what it would use (ADR 0027, port step 4).

The names and signatures match `posix.py`; tests/test_system.py keeps the two in step.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ClientHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


def _todo(what: str) -> NotImplementedError:
    return NotImplementedError(f"Milo's brain doesn't run on Windows yet: {what}")


def open_no_follow(path: Path) -> int:
    raise _todo("open the secret with CreateFileW and FILE_FLAG_OPEN_REPARSE_POINT, refusing reparse points")


def owned_by_me(info: os.stat_result) -> bool:
    raise _todo("compare the file's owner SID (GetSecurityInfo) with the process token's user SID")


def open_to_others(info: os.stat_result) -> bool:
    raise _todo("read the file's DACL and look for entries granting anyone but the user, SYSTEM and Administrators")


def make_private(target: int | Path, mode: int) -> None:
    raise _todo("set a protected DACL that grants the user alone (SetSecurityInfo)")


def try_lock(fd: int) -> bool:
    raise _todo("msvcrt.locking(fd, LK_NBLCK, 1), or a named mutex Local\\\\Milo-<workspace hash>")


def isolated_process() -> dict[str, Any]:
    raise _todo("CREATE_NEW_PROCESS_GROUP, and assign the child to a Job Object so its tree can be ended")


def signal_processes(root: int, tree: list[int], *, force: bool) -> None:
    raise _todo("CTRL_BREAK_EVENT to the group to ask, TerminateJobObject to force")


def process_table() -> dict[int, tuple[int, str]]:
    raise _todo("CreateToolhelp32Snapshot for parent pids and GetProcessTimes for start times")


async def start_local_server(client: ClientHandler, path: Path, *, limit: int | None = None) -> asyncio.Server:
    raise _todo("a named pipe \\\\.\\pipe\\milo-<name> with a DACL for the user (asyncio's ProactorEventLoop "
                "start_serving_pipe), or AF_UNIX, which Windows 10 1803+ has but CPython's asyncio doesn't serve")


def connect_local(path: Path, timeout_s: float | None = None) -> socket.socket:
    raise _todo("open the named pipe that start_local_server made")


def peer_is_me(sock: socket.socket | None) -> bool:
    raise _todo("GetNamedPipeClientProcessId, then the client process token's user SID")
