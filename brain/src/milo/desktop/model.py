"""The desktop's protocol state, independent of Qt and native APIs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ACTIVE_HELPER_STATES = frozenset(("queued", "working", "needs_you"))


@dataclass
class DesktopState:
    state: str = "idle"
    emotion: str = "neutral"
    bubble: str = ""
    heard: str = ""
    partial: str = ""
    level: float = 0.0
    connected: bool = False
    current: str = ""
    entries: dict[str, dict] = field(default_factory=dict)
    confirmations: dict[str, dict] = field(default_factory=dict)
    conversations: list[dict] = field(default_factory=list)
    search_results: list[dict] = field(default_factory=list)
    settings: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    routines: list[dict] = field(default_factory=list)
    drafts: list[dict] = field(default_factory=list)
    helpers: list[dict] = field(default_factory=list)
    undo_points: list[dict] = field(default_factory=list)
    reminders: list[dict] = field(default_factory=list)
    meeting: dict = field(default_factory=dict)
    meeting_lines: list[dict] = field(default_factory=list)
    meeting_notes: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    remote: dict = field(default_factory=dict)
    restart: bool = False
    error: str = ""
    hands_active: bool = False
    looking: bool = False

    def apply(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind in ("state", "emotion"):
            setattr(self, kind, str(event.get(kind, "")))
        elif kind in ("bubble", "heard", "partial"):
            setattr(self, kind, str(event.get("text", "")))
        elif kind in ("status", "access"):
            self.bubble = str(event.get("text", ""))
        elif kind == "level":
            self.level = min(1.0, max(0.0, float(event.get("value", 0))))
        elif kind in ("history", "conversation"):
            self.entries = {str(e["id"]): dict(e) for e in event.get("entries", [])}
            if kind == "conversation":
                self.current = str(event.get("id", ""))
        elif kind == "entry":
            entry = dict(event["entry"])
            self.entries[str(entry["id"])] = entry
        elif kind == "reply_delta":
            key = str(event["id"])
            entry = self.entries.setdefault(key, {"id": key, "kind": "milo", "text": ""})
            entry["text"] = str(entry.get("text", "")) + str(event.get("text", ""))
        elif kind == "confirm":
            self.confirmations[str(event["id"])] = dict(event)
        elif kind == "confirm_done":
            self.confirmations.pop(str(event["id"]), None)
        elif kind == "conversations":
            self.conversations = list(event.get("conversations", []))
            self.current = str(event.get("current", ""))
        elif kind == "search_results":
            self.search_results = list(event.get("results", []))
        elif kind in ("facts", "helpers", "reminders"):
            setattr(self, kind, list(event.get(kind, [])))
        elif kind == "undo_points":
            self.undo_points = list(event.get("points", []))
        elif kind == "routines":
            self.routines = list(event.get("routines", []))
            self.drafts = list(event.get("drafts", []))
        elif kind == "settings":
            if event.get("settings"):
                self.settings = list(event["settings"])
            self.restart = bool(event.get("restart", False))
            self.error = str(event.get("error", ""))
        elif kind == "meeting_status":
            if self.meeting.get("id") != event.get("id"):
                self.meeting_lines = []
                if event.get("id"):
                    self.meeting_notes = {}
            self.meeting = dict(event)
        elif kind == "meeting_lines":
            if event.get("reset"):
                self.meeting_lines = []
            self.meeting_lines.extend(event.get("lines", []))
        elif kind == "meeting_notes":
            self.meeting_notes = dict(event)
        elif kind in ("usage", "remote"):
            setattr(self, kind, dict(event))
        elif kind == "hands_session":
            self.hands_active = bool(event.get("on"))
        elif kind == "looking":
            self.looking = bool(event.get("on"))


def confirmation_answer(question: dict, choice: str) -> dict:
    """Only a real button invokes this; money approvals are never answered by a shortcut."""
    offered = question.get("choices") or ([{"id": "yes"}, {"id": "no"}] +
                                          ([{"id": "always"}] if question.get("always") else []))
    if choice not in {str(item["id"]) for item in offered}:
        raise ValueError("That answer isn't offered by this question")
    return {"type": "confirm_answer", "id": str(question["id"]),
            "yes": choice in ("yes", "always"), "always": choice == "always", "choice": choice}
