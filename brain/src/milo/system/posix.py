"""The OS primitives on macOS and Linux: flock, uids and modes, process groups, and Unix sockets."""

from __future__ import annotations

import asyncio
import fcntl
import os
import signal
import socket
import stat
import struct
import subprocess
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ClientHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


# ---- files: secrets and locks

def open_no_follow(path: Path) -> int:
    """Open `path` read-only without following a link (a link raises OSError with errno ELOOP)."""
    return os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)


def owned_by_me(info: os.stat_result) -> bool:
    """Whether this user owns the file or folder `info` describes."""
    return info.st_uid == os.getuid()


def open_to_others(info: os.stat_result) -> bool:
    """Whether its mode lets the group or other users in at all."""
    return bool(info.st_mode & 0o077)


def make_private(target: int | Path, mode: int) -> None:
    """chmod an open file (a descriptor) or a folder (a path, never through a link). Raises OSError."""
    if isinstance(target, int):
        os.fchmod(target, mode)
    else:
        os.chmod(target, mode, follow_symlinks=False)


def try_lock(fd: int) -> bool:
    """Take an exclusive lock on the open file `fd` without waiting. False if another process holds it. The
    kernel releases it when the process ends, however it ends."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


# ---- processes: harness CLIs and everything they start

def isolated_process() -> dict[str, Any]:
    """Keyword arguments for subprocess and asyncio.create_subprocess_exec: the child leads a group of its own,
    so it and what it starts can be signalled together."""
    return {"start_new_session": True}


def signal_processes(root: int, tree: list[int], *, force: bool) -> None:
    """Ask `root` and the processes it started (`tree`) to end, or kill them if `force`. Each as a group when it
    leads one. Processes that are gone or not ours are skipped."""
    sig = signal.SIGKILL if force else signal.SIGTERM
    for pid in (root, *tree):
        try:
            os.killpg(pid, sig)  # fails for a process that leads no group
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass


def process_table() -> dict[int, tuple[int, str]]:
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


# ---- local sockets: the app, the worker's tools and the hands server reach the brain

async def start_local_server(client: ClientHandler, path: Path, *, limit: int | None = None) -> asyncio.Server:
    """Serve on a Unix socket at `path` that only this user can reach: 0600 in a 0700 folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    # Bind under a restrictive umask so the socket is never more open than 0600, not even briefly.
    old_umask = os.umask(0o177)
    try:
        return await asyncio.start_unix_server(client, path=str(path),
                                               **({"limit": limit} if limit is not None else {}))
    finally:
        os.umask(old_umask)


def connect_local(path: Path, timeout_s: float | None = None) -> socket.socket:
    """A blocking client connection to the local server at `path`. Raises OSError if nobody serves there."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout_s)
        sock.connect(str(path))
    except BaseException:
        sock.close()
        raise
    return sock


_SOL_LOCAL, _LOCAL_PEERCRED = 0, 0x001  # macOS <sys/un.h>


def peer_is_me(sock: socket.socket | None) -> bool:
    """Whether the process on the other end runs as this user. On macOS LOCAL_PEERCRED always answers, so
    no answer is refused there; elsewhere the 0700 folder is the check."""
    uid = peer_uid(sock)
    return uid == os.getuid() if uid is not None or sys.platform == "darwin" else True


def peer_uid(sock: socket.socket | None) -> int | None:
    """UID of the process on the other end, or None if the OS can't tell us."""
    if sock is None:
        return None
    try:
        if hasattr(socket, "SO_PEERCRED"):  # Linux: struct ucred {pid, uid, gid}
            return struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
        cred = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, 76)  # macOS: struct xucred {version, uid, ...}
        return struct.unpack_from("=II", cred)[1]
    except OSError:
        return None
