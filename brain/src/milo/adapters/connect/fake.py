"""Made-up connections over one JSON file and a folder of files, for tests, the eval and trying Milo out.

Nothing here touches the user's real apps. `world.json` holds events, reminders, mail, notes and
shortcuts; `home/` holds the files. Every call re-reads the file, so a test can change the world between
calls, and every change is written back, so a test can check what Milo did.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from milo.core.ports import Connections
from milo.core.registry import CONNECTIONS, AdapterContext, options_from
from milo.core.types import ToolError

from . import _files

EMPTY_WORLD = {"events": [], "reminders": [], "mail": [], "drafts": [], "notes": [], "shortcuts": [],
               "shortcut_runs": []}


@dataclass(frozen=True)
class FakeOptions:
    dir: str = ""
    """Default: <MILO_HOME>/fake."""


class World:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "world.json"
        self.home = root / "home"

    def load(self) -> dict:
        if not self.path.exists():
            return json.loads(json.dumps(EMPTY_WORLD))
        return {**EMPTY_WORLD, **json.loads(self.path.read_text(encoding="utf-8"))}

    def save(self, world: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(world, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _matches(item: dict, query: str, *keys: str) -> bool:
    words = query.lower().split()
    text = " ".join(str(item.get(k, "")) for k in keys).lower()
    return all(w in text for w in words)


def _iso(dt: datetime | None) -> str:
    return dt.isoformat(timespec="minutes") if dt is not None else ""


class FakeCalendar:
    def __init__(self, world: World):
        self._world = world

    def events(self, start: datetime, end: datetime, query: str = "") -> list[dict]:
        found = [e for e in self._world.load()["events"]
                 if e["start"] < _iso(end) and e["end"] > _iso(start)
                 and (not query or _matches(e, query, "title", "location", "notes"))]
        return sorted(found, key=lambda e: e["start"])

    def add_event(self, title: str, start: datetime, end: datetime, location: str = "", notes: str = "",
                  calendar: str = "") -> dict:
        world = self._world.load()
        event = {"id": _new_id(), "title": title, "start": _iso(start), "end": _iso(end), "location": location,
                 "notes": notes, "calendar": calendar or "Home"}
        world["events"].append(event)
        self._world.save(world)
        return event


class FakeReminders:
    def __init__(self, world: World):
        self._world = world

    def list(self, query: str = "", include_done: bool = False) -> list[dict]:
        return [r for r in self._world.load()["reminders"]
                if (include_done or not r.get("done")) and (not query or _matches(r, query, "title", "notes"))]

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict:
        world = self._world.load()
        reminder = {"id": _new_id(), "title": title, "due": _iso(due), "notes": notes,
                    "list": list_name or "Reminders", "done": False}
        world["reminders"].append(reminder)
        self._world.save(world)
        return reminder

    def complete(self, id: str) -> dict:
        world = self._world.load()
        for r in world["reminders"]:
            if r["id"] == id:
                r["done"] = True
                self._world.save(world)
                return r
        raise ToolError("I couldn't find that reminder.")


class FakeMail:
    def __init__(self, world: World):
        self._world = world

    def search(self, query: str, limit: int = 20) -> list[dict]:
        found = [m for m in self._world.load()["mail"] if _matches(m, query, "from", "to", "subject")]
        found.sort(key=lambda m: m["date"], reverse=True)
        return [{k: m.get(k, "") for k in ("id", "from", "subject", "date", "mailbox")} for m in found[:limit]]

    def read(self, id: str) -> dict:
        for m in self._world.load()["mail"]:
            if m["id"] == id:
                return {k: m.get(k, "") for k in ("id", "from", "to", "subject", "date", "text")}
        raise ToolError("I couldn't find that in Mail any more.")

    def draft(self, to: list[str], subject: str, body: str, reply_to: str = "") -> dict:
        world = self._world.load()
        if reply_to:
            original = next((m for m in world["mail"] if m["id"] == reply_to), None)
            if original is None:
                raise ToolError("I couldn't find that in Mail any more.")
            to = to or [original["from"]]
            subject = subject or "Re: " + original["subject"]
        draft = {"id": _new_id(), "to": to, "subject": subject, "body": body, "reply_to": reply_to}
        world["drafts"].append(draft)
        self._world.save(world)
        return {"draft": True, "sent": False, "subject": subject, "to": to,
                "where": "Open in Mail for the user to check and send."}


class FakeNotes:
    def __init__(self, world: World):
        self._world = world

    def search(self, query: str, limit: int = 20) -> list[dict]:
        return [{k: n.get(k, "") for k in ("id", "title", "folder", "modified")}
                for n in self._world.load()["notes"] if _matches(n, query, "title", "body")][:limit]

    def read(self, id: str) -> dict:
        for n in self._world.load()["notes"]:
            if n["id"] == id:
                return {"id": id, "title": n["title"], "folder": n.get("folder", "Notes"), "text": n["body"]}
        raise ToolError("I couldn't find that note.")

    def create(self, title: str, body: str, folder: str = "") -> dict:
        world = self._world.load()
        note = {"id": _new_id(), "title": title, "folder": folder or "Notes", "body": body,
                "modified": datetime.now().isoformat(timespec="minutes")}
        world["notes"].append(note)
        self._world.save(world)
        return {"id": note["id"], "title": title}

    def append(self, id: str, text: str) -> dict:
        world = self._world.load()
        for n in world["notes"]:
            if n["id"] == id:
                n["body"] = n["body"].rstrip("\n") + "\n" + text
                self._world.save(world)
                return {"id": id, "title": n["title"], "appended": True}
        raise ToolError("I couldn't find that note.")


class FakeShortcuts:
    def __init__(self, world: World):
        self._world = world

    def list(self) -> list[str]:
        return [s["name"] for s in self._world.load()["shortcuts"]]

    def run(self, name: str, input_text: str = "") -> str:
        world = self._world.load()
        shortcut = next((s for s in world["shortcuts"] if s["name"] == name), None)
        if shortcut is None:
            raise ToolError(f"There's no shortcut called “{name}”.")
        world["shortcut_runs"].append({"name": name, "input": input_text})
        self._world.save(world)
        return str(shortcut.get("output", ""))


class FakeFiles:
    """Files under the fake home, found by name and by content like Spotlight would."""

    def __init__(self, world: World):
        self.scope = world.home

    def find(self, name: str, limit: int = 20) -> list[dict]:
        return _files.newest([p for p in self._all() if name.lower() in p.name.lower()], self.scope, limit)

    def search(self, text: str, limit: int = 20) -> list[dict]:
        words = text.lower().split()
        hits = []
        for p in self._all():
            try:
                content = (p.name + " " + _files.text_of(p)).lower()
            except ToolError:
                continue
            if all(w in content for w in words):
                hits.append(p)
        return _files.newest(hits, self.scope, limit)

    def read(self, path: str, max_chars: int = 20000) -> dict:
        return _files.read(_files.checked(path, self.scope), max_chars)

    def _all(self) -> list[Path]:
        if not self.scope.is_dir():
            return []
        return [p for p in self.scope.rglob("*") if p.is_file() and _files.allowed(p, self.scope)]


@CONNECTIONS.register("fake")
def _fake(options: Mapping[str, Any], ctx: AdapterContext) -> Connections:
    o = options_from(FakeOptions, options, "connections.fake")
    world = World(Path(o.dir).expanduser() if o.dir else ctx.home / "fake")
    return Connections(calendar=FakeCalendar(world), reminders=FakeReminders(world), mail=FakeMail(world),
                       notes=FakeNotes(world), shortcuts=FakeShortcuts(world), files=FakeFiles(world))
