"""Facts: memory/facts.jsonl, an append-only log of changes. Never rewritten, so every change can be undone.

    {"op": "add", "id": ..., "text": ..., "topic": ..., "since": ..., "source": ..., "replaces": ..., "by": ...}
    {"op": "retire", "id": ..., "reason": ..., "on": ..., "by": ...}
    {"op": "restore", "id": ..., "reason": ..., "on": ..., "by": ...}

`by` says who made the change: "chat", "you", "worker", "sleep:<day>:<run>", ... Another process (the
consolidation run by hand) may append too: the store notices the file grew and reads the new lines.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from milo.core.memory import Fact

from . import jsonl

log = logging.getLogger(__name__)


FORGOTTEN_BY = ("you", "worker")
"""Who retires a fact when the user asks Milo to forget it."""


class JsonlFactStore:
    """FactStore over facts.jsonl, held in memory and caught up from the file when it changes."""

    def __init__(self, path: Path, clock=None):
        self.path = path
        self._clock = clock
        self._facts: dict[str, Fact] = {}
        """Every fact ever added, with `retired` as it is now. Insertion order is the order they came."""
        self._changes: list[dict] = []
        self._offset = 0
        self._seen: tuple[int, int] | None = None  # (inode, size) read so far
        self._lock = threading.RLock()  # the event loop writes while the memory thread reads

    def current(self) -> list[Fact]:
        with self._lock:
            self._catch_up()
            replaced = {f.replaces for f in self._facts.values() if f.replaces and not f.retired}
            return [f for f in self._facts.values() if not f.retired and f.id not in replaced]

    def get(self, id: str) -> Fact | None:
        with self._lock:
            self._catch_up()
            return self._facts.get(id)

    def forgotten(self) -> list[Fact]:
        with self._lock:
            self._catch_up()
            ids = [c["id"] for c in reversed(self._changes) if c.get("op") == "retire" and c.get("by") in FORGOTTEN_BY]
            facts = (self._facts.get(id) for id in dict.fromkeys(ids))
            return [f for f in facts if f is not None and f.retired]

    def changes(self) -> list[dict]:
        """Every line read so far, oldest first."""
        with self._lock:
            self._catch_up()
            return list(self._changes)

    def add(self, fact: Fact, *, by: str = "") -> None:
        self._write({"op": "add", **fact.to_dict(), **({"by": by} if by else {})})

    def retire(self, id: str, reason: str, *, by: str = "") -> None:
        if self.get(id) is None:
            raise KeyError(id)
        self._write({"op": "retire", "id": id, "reason": reason, "on": self._now(), **({"by": by} if by else {})})

    def restore(self, id: str, reason: str, *, by: str = "") -> None:
        if self.get(id) is None:
            raise KeyError(id)
        self._write({"op": "restore", "id": id, "reason": reason, "on": self._now(), **({"by": by} if by else {})})

    def _now(self) -> str:
        now = self._clock.now() if self._clock is not None else datetime.now()
        return now.isoformat(timespec="seconds")

    def _write(self, record: dict) -> None:
        with self._lock:
            self._catch_up()
            jsonl.append(self.path, record, sync=True)
            self._catch_up()

    def _catch_up(self) -> None:
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            if self._seen is not None:
                self._reset()
            return
        if self._seen == (st.st_ino, st.st_size):
            return
        if self._seen is not None and (st.st_ino != self._seen[0] or st.st_size < self._offset):
            self._reset()  # replaced or cut: read it again from the start
        records, self._offset = jsonl.read(self.path, self._offset)
        for record in records:
            self._apply(record)
        self._seen = (st.st_ino, st.st_size)

    def _reset(self) -> None:
        self._facts, self._changes, self._offset, self._seen = {}, [], 0, None

    def _apply(self, record: dict) -> None:
        op, id = record.get("op"), record.get("id")
        if not id:
            return
        try:
            if op == "add":
                self._facts[id] = Fact.from_dict(record)
            elif op in ("retire", "restore") and id in self._facts:
                self._facts[id] = replace(self._facts[id], retired=op == "retire")
            else:
                return
        except (KeyError, TypeError, ValueError):
            log.warning("skipping a malformed line in %s", self.path.name)
            return
        self._changes.append(record)
