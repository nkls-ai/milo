"""The conversation the Milo window shows, one JSON object per line, kept across restarts."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_BLOCK = 16 * 1024


class JsonlTranscript:
    """TranscriptStore appending finished entries to a JSONL file. tail() reads the file from the end."""

    def __init__(self, path: Path):
        self.path = path

    def append(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def tail(self, n: int) -> list[dict]:
        if n <= 0:
            return []
        try:
            lines = _last_lines(self.path, n)
        except FileNotFoundError:
            return []
        entries = []
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                log.warning("skipping a broken line in %s", self.path)
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries


def _last_lines(path: Path, n: int) -> list[bytes]:
    """The last n non-empty lines, reading backwards block by block so a long file costs no more than a short one."""
    with path.open("rb") as f:
        end = f.seek(0, os.SEEK_END)
        pos, data = end, b""
        while pos > 0 and data.count(b"\n") <= n:
            step = min(_BLOCK, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
    lines = [line for line in data.split(b"\n") if line.strip()]
    if pos > 0:
        lines = lines[1:]  # the first one may be cut off
    return lines[-n:]
