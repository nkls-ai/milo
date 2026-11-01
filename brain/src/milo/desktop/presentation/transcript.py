"""What the Milo window shows of the conversations (MiloKit/TranscriptModel.swift), on wire dicts.

Built from `conversations`, `conversation`, `history`, `entry`, `reply_delta`, `activity`, `search_results` and
`reminders`. Every change is reported as a small `Change`, so a list view updates one row while a reply streams
instead of laying out the whole thread again. See docs/design/conversations.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

LIMIT = 200  # entries kept per conversation; the brain sends fewer on connect


@dataclass(frozen=True)
class Change:
    """kind: "reset" (the conversation's entries are new), "insert"/"update" (one row at `index`),
    "trim" (`index` rows went from the front), or "current" (the conversation going on is now `conversation`)."""
    kind: str
    conversation: str
    index: int = 0


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Transcript:
    def __init__(self, on_change: Callable[[Change], None] | None = None):
        self.entries: list[dict] = []
        self.conversations: list[dict] = []
        self.current = ""
        self.more = False
        self.opened: dict[str, list[dict]] = {}
        self.search_query = ""
        self.search_results: list[dict] = []
        self.reminders: list[dict] = []
        self._notify = on_change or (lambda change: None)

    # ---- reading

    def info(self, conversation: str) -> dict | None:
        return next((c for c in self.conversations if c.get("id") == conversation), None)

    def entries_of(self, conversation: str) -> list[dict]:
        return self.entries if conversation == self.current else self.opened.get(conversation, [])

    def task(self, task_id: str) -> tuple[dict, dict | None] | None:
        """A task entry wherever it is, and the conversation that asked for it."""
        for entry in reversed(self.entries):
            if entry.get("id") == task_id:
                return entry, self.info(entry.get("conversation") or self.current)
        for conversation, rows in self.opened.items():
            for entry in reversed(rows):
                if entry.get("id") == task_id:
                    return entry, self.info(conversation)
        return None

    def conversation_of_task(self, task_id: str) -> dict | None:
        return next((c for c in self.conversations
                     if any(t.get("id") == task_id for t in c.get("tasks") or [])), None)

    # ---- events

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "history":
            rows = [dict(e) for e in event.get("entries") or []]
            last = rows[-1].get("conversation", "") if rows else ""
            if last and last != self.current:
                self._switch(last)
            self.entries = rows[-LIMIT:]
            self._notify(Change("reset", self.current))
        elif kind == "entry":
            self._upsert(dict(event.get("entry") or {}))
        elif kind == "reply_delta":
            self._delta(str(event.get("id", "")), str(event.get("text", "")))
        elif kind == "activity":
            self._step(str(event.get("task_id", "")), dict(event.get("step") or {}))
        elif kind == "conversations":
            self.conversations = [dict(c) for c in event.get("conversations") or []]
            self.more = bool(event.get("more", False))
            current = str(event.get("current", ""))
            if current != self.current:
                self._switch(current)
        elif kind == "conversation":
            self._conversation(dict(event.get("info") or {"id": event.get("id", "")}),
                               [dict(e) for e in event.get("entries") or []])
        elif kind == "search_results":
            self.search_query = str(event.get("query", ""))
            self.search_results = list(event.get("results") or [])
        elif kind == "reminders":
            self.reminders = list(event.get("reminders") or [])

    def clear_search(self) -> None:
        self.search_query, self.search_results = "", []

    # ---- the pieces

    def _conversation(self, info: dict, rows: list[dict]) -> None:
        cid = str(info.get("id", ""))
        known = next((i for i, c in enumerate(self.conversations) if c.get("id") == cid), None)
        if known is not None:
            self.conversations[known] = info
        else:
            self.conversations.append(info)
            self.conversations.sort(key=lambda c: str(c.get("last", "")), reverse=True)
        if cid == self.current:
            # Keep what streams right now; the brain's copy has the rest.
            ids = {e.get("id") for e in rows}
            live = [e for e in self.entries if e.get("id") not in ids]
            self.entries = sorted(rows + live, key=lambda e: str(e.get("ts", "")))[-LIMIT:]
        else:
            self.opened[cid] = rows[-LIMIT:]
        self._notify(Change("reset", cid))

    def _upsert(self, entry: dict) -> None:
        """A new user turn in a conversation the window doesn't know yet starts the next one: the brain's list,
        which says so too, comes a moment later."""
        cid = str(entry.get("conversation", ""))
        if not cid or cid == self.current:
            index = self._index(self.entries, entry.get("id"))
            if index is None:
                self._append(entry)
            else:
                self.entries[index] = entry
                self._notify(Change("update", self.current, index))
            return
        known = self.info(cid) is not None or cid in self.opened
        if not known and entry.get("kind") == "user":
            self._switch(cid)
            self._append(entry)
            return
        rows = self.opened.setdefault(cid, [])
        index = self._index(rows, entry.get("id"))
        if index is None:
            rows.append(entry)
            self._notify(Change("insert", cid, len(rows) - 1))
        else:
            rows[index] = entry
            self._notify(Change("update", cid, index))

    def _delta(self, entry_id: str, text: str) -> None:
        found = self._find(entry_id)
        if found is None:
            self._append({"id": entry_id, "ts": now_ts(), "kind": "milo", "text": text, "done": False,
                          "conversation": self.current})
            return
        cid, index = found
        row = self.entries_of(cid)[index]
        row["text"] = str(row.get("text", "")) + text
        self._notify(Change("update", cid, index))

    def _step(self, task_id: str, step: dict) -> None:
        found = self._find(task_id)
        if found is None:
            return
        cid, index = found
        row = self.entries_of(cid)[index]
        steps = list(row.get("steps") or [])
        at = next((i for i, s in enumerate(steps) if s.get("id") == step.get("id")), None)
        if at is None:
            steps.append(step)
        else:
            steps[at] = step
        row["steps"] = steps
        self._notify(Change("update", cid, index))

    def _switch(self, conversation: str) -> None:
        if self.current:
            self.opened[self.current] = self.entries
        self.current = conversation
        self.entries = self.opened.pop(conversation, [])
        self._notify(Change("current", conversation))

    def _find(self, entry_id: str) -> tuple[str, int] | None:
        index = self._index(self.entries, entry_id)
        if index is not None:
            return self.current, index
        for cid, rows in self.opened.items():
            index = self._index(rows, entry_id)
            if index is not None:
                return cid, index
        return None

    @staticmethod
    def _index(rows: list[dict], entry_id) -> int | None:
        for i in range(len(rows) - 1, -1, -1):
            if rows[i].get("id") == entry_id:
                return i
        return None

    def _append(self, entry: dict) -> None:
        self.entries.append(entry)
        self._notify(Change("insert", self.current, len(self.entries) - 1))
        if len(self.entries) > LIMIT:
            extra = len(self.entries) - LIMIT
            del self.entries[:extra]
            self._notify(Change("trim", self.current, extra))
