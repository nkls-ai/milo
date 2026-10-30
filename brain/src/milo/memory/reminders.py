"""Reminders live in <home>/reminders.md as `- [ ] YYYY-MM-DD HH:MM text` lines.

Milo's chat tags and the worker's milo_remind tool (with the user's yes, ADR 0020) add them, and the user may
edit the file; the heartbeat fires them locally, so a reminder costs no tokens.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path

from milo.core.types import Reminder

_LINE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s+(.+?)\s*$")


def parse(markdown: str) -> list[Reminder]:
    """Every well-formed reminder line, in file order. Other lines and impossible dates are skipped."""
    out = []
    for line in markdown.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        mark, day, clock, text = m.groups()
        try:
            due = datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        # Stable across edits elsewhere in the file, so "already fired" survives re-parsing.
        rid = hashlib.sha1(f"{day} {clock} {text}".encode()).hexdigest()[:12]
        out.append(Reminder(id=rid, due=due, text=text, done=mark.lower() == "x"))
    return out


class MarkdownReminders:
    """ReminderSource over reminders.md. Re-reads only when the mtime changes, so a tick costs one stat()."""

    def __init__(self, path: Path):
        self.path = path
        self._mtime: int | None = None
        self._items: list[Reminder] = []

    def all(self) -> list[Reminder]:
        try:
            mtime = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            self._mtime, self._items = None, []
            return []
        if mtime != self._mtime:
            self._items = parse(self.path.read_text(encoding="utf-8", errors="replace"))
            self._mtime = mtime
        return self._items

    def add(self, due: datetime, text: str) -> Reminder:
        """Append `- [ ] YYYY-MM-DD HH:MM text` and return it as all() will report it."""
        text = " ".join(text.split())
        if not text:
            raise ValueError("a reminder needs text")
        line = f"- [ ] {due:%Y-%m-%d %H:%M} {text}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = self.path.read_bytes()
        except FileNotFoundError:
            existing = b""
        with self.path.open("a", encoding="utf-8") as f:
            f.write(("\n" if existing and not existing.endswith(b"\n") else "") + line + "\n")
        self._mtime = None  # re-read next time even if the mtime did not visibly change
        return parse(line)[0]
