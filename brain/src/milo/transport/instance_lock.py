"""One brain per workspace. Two would each load Whisper and OmniVoice, and on 16 GB the pair fills swap."""

from __future__ import annotations

import os
from pathlib import Path

from milo import system


class AlreadyRunning(Exception):
    """Another process holds the lock. `pid` is what it wrote there, if anything."""

    def __init__(self, path: Path, pid: int | None):
        super().__init__(f"another Milo brain (pid {pid or '?'}) is running or starting; lock {path}")
        self.pid = pid


def acquire(path: Path) -> int:
    """Take the lock or raise AlreadyRunning. Returns the open file descriptor: keep it open for the
    process's lifetime. The kernel releases the lock when the process ends, however it ends."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    if not system.try_lock(fd):
        pid = _read_pid(fd)
        os.close(fd)
        raise AlreadyRunning(path, pid)
    os.ftruncate(fd, 0)
    os.pwrite(fd, f"{os.getpid()}\n".encode(), 0)
    return fd


def _read_pid(fd: int) -> int | None:
    try:
        return int(os.pread(fd, 32, 0).decode().strip())
    except (OSError, ValueError):
        return None
