"""The window's left side and a conversation's header (MiloKit/ConversationsSidebar.swift, ConversationPage.swift).

Rows are plain dicts for QML: the conversations by day, each hanging on a thread with a bead.
"""
from __future__ import annotations

from datetime import datetime

from . import dates


def from_phone(info: dict) -> bool:
    return "message" in (info.get("via") or [])


def working(info: dict) -> bool:
    return any(t.get("status") == "running" for t in info.get("tasks") or [])


def kind_mark(info: dict) -> str:
    """The small sign before a title: "meeting", "routine", "phone" or ""."""
    kind = info.get("kind", "chat")
    if kind in ("meeting", "routine"):
        return kind
    return "phone" if from_phone(info) else ""


def bead(info: dict, live: bool) -> str:
    """rest, live (a ring that breathes), working (marigold), or failed."""
    if working(info):
        return "working"
    if live:
        return "live"
    return "failed" if any(t.get("status") == "failed" for t in info.get("tasks") or []) else "rest"


def meeting_line(info: dict, meeting: dict) -> tuple[str, bool] | None:
    """What a meeting's row says under its title while its notes are taken; None otherwise."""
    if info.get("kind") != "meeting" or not meeting.get("id"):
        return None
    source = str(info.get("source", ""))
    if meeting.get("conversation") != info.get("id") and source != f"meeting:{meeting['id']}":
        return None
    phase = meeting.get("phase", "")
    if phase not in ("recording", "paused", "writing"):
        return None
    words = {"writing": "Writing the notes…", "paused": "Notes paused"}.get(phase, "Taking notes now")
    return words, phase in ("recording", "paused")


def subtitle(info: dict, meeting: dict | None = None) -> tuple[str, bool]:
    """The line under a row's title, and whether it shows something going on now."""
    line = meeting_line(info, meeting or {})
    if line is not None:
        return line
    running = [t for t in info.get("tasks") or [] if t.get("status") == "running"]
    if running:
        title = running[-1].get("title", "")
        return ("Working on it…" if title == info.get("title") else f"Working on “{title}”…"), True
    if info.get("preview"):
        return str(info["preview"]), False
    kind, turns = info.get("kind", "chat"), int(info.get("turns", 0) or 0)
    if kind == "meeting":
        return "Meeting notes", False
    if kind == "routine":
        return "Ran on its schedule", False
    return ("1 message" if turns == 1 else f"{turns} messages"), False


def rows(conversations: list[dict], current: str, now: datetime, meeting: dict | None = None) -> list[dict]:
    """The list, latest first, grouped by day. `section` names each row's group; first/last end its thread."""
    ordered = sorted(conversations, key=lambda c: str(c.get("last", "")), reverse=True)
    out: list[dict] = []
    for info in ordered:
        last = dates.parse(info.get("last")) or now
        section = dates.heading(last, now)
        live = info.get("id") == current
        line, active = subtitle(info, meeting)
        first = not out or out[-1]["section"] != section
        if not first:
            out[-1]["last"] = False
        out.append({
            "id": str(info.get("id", "")),
            "title": info.get("title") or "A conversation",
            "time": dates.short(last, now),
            "subtitle": line,
            "active": active,
            "mark": kind_mark(info),
            "bead": bead(info, live),
            "live": live,
            "section": section,
            "first": first,
            "last": True,
        })
    return out


def search_rows(results: list[dict], now: datetime) -> list[dict]:
    out = []
    for hit in results:
        at = dates.parse(hit.get("at")) or now
        out.append({"id": str(hit.get("conversation", "")), "title": hit.get("title", ""),
                    "time": dates.short(at, now), "snippet": hit.get("snippet", ""),
                    "mark": kind_mark({"kind": hit.get("kind", "chat"), "via": hit.get("via") or []})})
    return out


def header(info: dict, now: datetime) -> dict:
    """A conversation's title bar: "Today 9:12 · 6 turns · 1 task · from your phone"."""
    started = dates.parse(info.get("started")) or now
    day = dates.heading(started, now)
    when = (f"{day} " if day in ("Today", "Yesterday")
            else f"{started.strftime('%a')} {started.day} {started.strftime('%b')} ") + dates.clock(started)
    parts = [when]
    kind, turns, tasks = info.get("kind", "chat"), int(info.get("turns", 0) or 0), info.get("tasks") or []
    if kind == "meeting":
        parts.append("meeting notes")
    elif kind == "routine":
        parts.append("routine run")
    elif turns > 0:
        parts.append("1 turn" if turns == 1 else f"{turns} turns")
    if tasks:
        parts.append("1 task" if len(tasks) == 1 else f"{len(tasks)} tasks")
    if from_phone(info):
        parts.append("from your phone")
    return {"id": str(info.get("id", "")), "title": info.get("title") or "A conversation",
            "subtitle": " · ".join(parts), "mark": kind_mark(info) or "chat",
            "warm": kind != "chat" or from_phone(info)}
