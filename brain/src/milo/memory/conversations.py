"""The Milo window's conversations on disk: one JSONL file per conversation, and an index of their headers.

    state/conversations/index.jsonl                 a header line per change; the last line per id wins
    state/conversations/2026-10/c-5f2a9c1e04b7.jsonl {"header": {...}}, then entries, {"title": ...} lines

The conversation files are the truth; the index is a cache rebuilt from them when it is missing or doesn't
match the files. See docs/design/conversations.md and ADR 0019.
"""

from __future__ import annotations

import bisect
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from milo.core.conversations import (ConversationInfo, Recent, SplitRules, clean_title, conversation_id, recent_words,
                                     split, task_title, title_from)
from milo.core.memory import new_id
from milo.core.times import parse_local

from . import jsonl

log = logging.getLogger(__name__)

INDEX = "index.jsonl"
COMPACT_FACTOR = 4
"""Rewrite the index when it holds this many lines per conversation."""


class JsonlConversationStore:
    """ConversationStore over state/conversations/. Loads the index on first use."""

    def __init__(self, root: Path):
        self.root = root
        self._headers: dict[str, ConversationInfo] | None = None
        self._sorted: list[ConversationInfo] | None = None
        self._lines = 0

    # ---- writing

    def append(self, conversation: ConversationInfo, entry: dict) -> ConversationInfo:
        headers = self._load()
        known = headers.get(conversation.id)
        path = self._path(conversation)
        if known is None and not path.exists():
            jsonl.append(path, {"header": conversation.to_dict()})
        if conversation.outside and (known is None or not known.outside):
            jsonl.append(path, {"outside": True})
        jsonl.append(path, {**entry, "conversation": conversation.id})
        info = conversation.with_entry(entry)
        self._put(info)
        return info

    def save(self, conversation: ConversationInfo) -> None:
        if conversation.id in self._load() and conversation.outside and not self._load()[conversation.id].outside:
            jsonl.append(self._path(conversation), {"outside": True})
        self._put(conversation)

    def title(self, id: str, title: str, by: str) -> ConversationInfo | None:
        info = self._load().get(id)
        title = clean_title(title)
        if info is None or not title:
            return None
        if info.titled_by == "you" and by != "you":
            return info  # the user's own name stays
        jsonl.append(self._path(info), {"title": title, "by": by})
        info = replace(info, title=title, titled_by=by)
        self._put(info)
        return info

    # ---- reading

    def all(self) -> list[ConversationInfo]:
        if self._sorted is None:
            self._sorted = sorted(self._load().values(), key=lambda c: (c.last, c.started), reverse=True)
        return list(self._sorted)

    def get(self, id: str) -> ConversationInfo | None:
        return self._load().get(id)

    def entries(self, id: str, limit: int | None = None) -> list[dict]:
        info = self.get(id)
        if info is None:
            return []
        entries = _entries(jsonl.read_all(self._path(info)))
        return entries if limit is None else entries[-limit:] if limit > 0 else []

    def search_text(self, words: Sequence[str], *, limit: int = 20,
                    budget_bytes: int = 8_000_000) -> list[tuple[str, dict]]:
        words = [w.lower() for w in words if w.strip()]
        if not words:
            return []
        found: list[tuple[str, dict]] = []
        spent = 0
        for info in self.all():
            path = self._path(info)
            try:
                spent += path.stat().st_size
            except FileNotFoundError:
                continue
            if spent > budget_bytes:
                break
            for entry in reversed(_entries(jsonl.read_all(path))):
                text = f"{entry.get('text', '')} {entry.get('result', '')}".lower()
                if all(w in text for w in words):
                    found.append((info.id, entry))
                    break  # one hit per conversation
            if len(found) >= limit:
                break
        return found

    def rebuild(self) -> int:
        """Rebuild the index from the conversation files. Returns how many conversations there are."""
        headers: dict[str, ConversationInfo] = {}
        for path in sorted(self.root.glob("*/*.jsonl")):
            info = header_of(jsonl.read_all(path), path.stem)
            if info is not None:
                headers[info.id] = info
        self._headers, self._sorted = headers, None
        self._write_index()
        return len(headers)

    # ---- inside

    def _put(self, info: ConversationInfo) -> None:
        headers = self._load()
        headers[info.id] = info
        self._sorted = None
        jsonl.append(self.root / INDEX, info.to_dict())
        self._lines += 1
        if self._lines > max(200, COMPACT_FACTOR * len(headers)):
            self._write_index()

    def _write_index(self) -> None:
        headers = self._headers or {}
        text = "".join(json.dumps(h.to_dict(), ensure_ascii=False) + "\n" for h in headers.values())
        jsonl.write_private(self.root / INDEX, text)
        self._lines = len(headers)

    def _load(self) -> dict[str, ConversationInfo]:
        if self._headers is not None:
            return self._headers
        headers: dict[str, ConversationInfo] = {}
        lines = jsonl.read_all(self.root / INDEX)
        for d in lines:
            try:
                info = ConversationInfo.from_dict(d)
            except (KeyError, TypeError, ValueError):
                continue
            headers[info.id] = info
        self._headers, self._lines = headers, len(lines)
        files = {p.stem for p in self.root.glob("*/*.jsonl")}
        if files != set(headers):
            log.info("the conversation index doesn't match the files (%d against %d); rebuilding it",
                     len(headers), len(files))
            self.rebuild()
        return self._headers

    def _path(self, info: ConversationInfo) -> Path:
        return self.root / info.month / f"{info.id}.jsonl"


def _entries(lines: list[dict]) -> list[dict]:
    """The entries among a conversation file's lines, by time (a long task finishes after later turns)."""
    entries = [d for d in lines if "kind" in d and "id" in d and "ts" in d]
    return sorted(entries, key=lambda d: str(d.get("ts", "")))


def header_of(lines: list[dict], id: str) -> ConversationInfo | None:
    """A conversation's header, rebuilt from the lines of its file."""
    info: ConversationInfo | None = None
    for line in lines:
        if "header" in line and info is None:
            try:
                info = replace(ConversationInfo.from_dict(line["header"]), via=(), turns=0, tasks=(), preview="")
                info = replace(info, last=info.started)
            except (KeyError, TypeError, ValueError):
                info = None
        elif "title" in line and "kind" not in line and info is not None:
            info = replace(info, title=clean_title(line["title"]) or info.title,
                           titled_by=str(line.get("by") or "words"))
        elif line.get("outside") is True and "kind" not in line and info is not None:
            info = replace(info, outside=True)
    entries = _entries(lines)
    if info is None:
        if not entries:
            return None
        first = entries[0]
        info = ConversationInfo(id, "chat", str(first["ts"]), str(first["ts"]), _title_of(entries))
    for entry in entries:
        try:
            info = info.with_entry(entry)
        except (KeyError, TypeError, ValueError):
            continue
    return info


def _title_of(entries: Sequence[dict]) -> str:
    user = next((e for e in entries if e.get("kind") == "user" and str(e.get("text", "")).strip()), None)
    if user is not None:
        return title_from(str(user["text"]))
    task = next((e for e in entries if e.get("kind") == "task"), None)
    if task is not None:
        return task_title(task)
    milo = next((e for e in entries if str(e.get("text", "")).strip()), None)
    return title_from(str(milo["text"])) if milo is not None else "A conversation"


# ---- the one-time move from state/transcript.jsonl

_MEETING_NOTES = re.compile(r"^Notes from “(.+?)”:")


def migrate(transcript: Path, kept: Path, store: JsonlConversationStore, rules: SplitRules = SplitRules()) -> int:
    """Move the old one-scroll transcript into conversations, without losing a line. Returns the lines moved.

    Deterministic: conversation ids come from their first entry, and each file is written whole, so a crash
    halfway just runs it again with the same result. The old file is kept as `kept` (appended to, if an older
    Milo wrote a new transcript.jsonl after an earlier migration).
    """
    try:
        raw = transcript.read_bytes()
    except FileNotFoundError:
        return 0
    good: list[tuple[int, dict]] = []
    broken: list[tuple[int, str]] = []
    for n, line in enumerate(raw.split(b"\n")):
        line = line.removesuffix(b"\r")  # CRLF is a line ending on disk too
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        if isinstance(entry, dict) and "id" in entry and "kind" in entry and "ts" in entry:
            good.append((n, entry))
        else:
            broken.append((n, line.decode("utf-8", "replace")))
    good.sort(key=lambda p: str(p[1]["ts"]))

    drafts: list[tuple[ConversationInfo, list[dict]]] = []
    line_to: dict[int, int] = {}
    current: int | None = None
    recent: Recent | None = None
    texts: list[str] = []
    for n, entry in good:
        at = _time(entry["ts"])
        text = str(entry.get("text", ""))
        meeting = _MEETING_NOTES.match(text) if entry.get("kind") == "milo" else None
        if meeting is not None:
            drafts.append((ConversationInfo(conversation_id(str(entry["id"])), "meeting", str(entry["ts"]),
                                            str(entry["ts"]), clean_title(meeting.group(1))), [entry]))
            line_to[n] = len(drafts) - 1
            continue
        if entry.get("kind") == "user":
            why = split(rules, recent, text, str(entry.get("via") or "voice"), at)
        else:
            why = "first" if recent is None or (at - recent.last).total_seconds() > rules.idle_s else None
        if why is not None or current is None:
            drafts.append((ConversationInfo(conversation_id(str(entry["id"])), "chat", str(entry["ts"]),
                                            str(entry["ts"])), []))
            current, texts = len(drafts) - 1, []
            recent = Recent(at, 0)
        drafts[current][1].append(entry)
        line_to[n] = current
        texts.append(text)
        turns = recent.turns + (entry.get("kind") == "user")
        via = str(entry.get("via") or "voice") if entry.get("kind") == "user" else recent.via
        recent = Recent(max(recent.last, at), turns, recent_words(texts), via)

    if broken and not drafts:
        stamp = new_id()
        drafts.append((ConversationInfo(conversation_id(stamp.lower()), "chat", "1970-01-01T00:00:00",
                                        "1970-01-01T00:00:00", "Unreadable lines"), []))
    placed = sorted(line_to)
    for n, line in broken:  # with the conversation of the readable line before it in the file
        k = bisect.bisect_left(placed, n)
        drafts[line_to[placed[k - 1]] if k else 0][1].append({"broken": line})

    for info, entries in drafts:
        readable = [e for e in entries if "broken" not in e]
        if not info.title:
            info = replace(info, title=_title_of(readable) if readable else "Unreadable lines")
        body = [{"header": info.to_dict()}] + [e if "broken" in e else {**e, "conversation": info.id} for e in entries]
        jsonl.write_private(store.root / info.month / f"{info.id}.jsonl",
                            "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in body))
    store.rebuild()
    if kept.exists():
        with kept.open("ab") as f:
            f.write(raw if raw.endswith(b"\n") or not raw else raw + b"\n")
        transcript.unlink()
    else:
        transcript.rename(kept)
    log.info("moved %d transcript lines into %d conversations", len(good) + len(broken), len(drafts))
    return len(good) + len(broken)


def _time(ts: object) -> datetime:
    return parse_local(ts) or datetime.fromtimestamp(0)
