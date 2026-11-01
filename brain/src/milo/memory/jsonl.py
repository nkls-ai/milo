"""Append-only JSON lines that survive a crash mid-write.

A crash can leave a half-written last line. Readers skip it, and the next append starts on a fresh line, so
the broken line never swallows a good one.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path

from milo import system

log = logging.getLogger(__name__)


def append(path: Path, record: dict, *, sync: bool = False) -> None:
    """Add one line. `sync` also waits for the disk, for records that must survive a power cut."""
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
    system.make_private(path, 0o600)
    try:
        size = os.fstat(fd).st_size
        os.lseek(fd, max(0, size - 1), os.SEEK_SET)
        if size and os.read(fd, 1) != b"\n":
            line = b"\n" + line  # a crash cut the last line short
        os.write(fd, line)
        if sync:
            os.fsync(fd)
    finally:
        os.close(fd)


def read(path: Path, offset: int = 0) -> tuple[list[dict], int]:
    """The records from byte `offset` on, and the offset after the last complete line.

    A last line without its newline is left for later: it is either still being written or broken, and the
    next append starts after it on its own line. Lines that aren't JSON objects are skipped with a warning.
    """
    try:
        with path.open("rb") as f:
            f.seek(offset)
            data = f.read()
    except FileNotFoundError:
        return [], 0
    end = data.rfind(b"\n") + 1
    records = list(_parse(data[:end], path))
    return records, offset + end


def read_all(path: Path) -> list[dict]:
    """Every readable record, including a complete last line that only lacks its newline."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return []
    return list(_parse(data, path))


def _parse(data: bytes, path: Path) -> Iterator[dict]:
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            log.warning("skipping a broken line in %s", path.name)
            continue
        if isinstance(record, dict):
            yield record


def write_private(path: Path, text: str) -> None:
    """Replace `path` with `text` in one step, readable by the user only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    system.make_private(tmp, 0o600)
    system.replace_file(tmp, path)
