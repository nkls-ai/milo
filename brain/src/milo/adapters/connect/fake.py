"""Made-up connections over one JSON file and a folder of files, for tests, the eval and trying Milo out.

Nothing here touches the user's real apps. `world.json` holds events, reminders, mail, notes,
shortcuts, a home and the Focus; `home/` holds the files. Every call re-reads the file, so a test can change the world between
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

from milo.core.control import Protected
from milo.core.home import Device, NotSetUp
from milo.core.ports import Connections
from milo.core.registry import CONNECTIONS, AdapterContext, options_from
from milo.core.types import ToolError

from . import _files

EMPTY_WORLD = {"events": [], "reminders": [], "mail": [], "drafts": [], "notes": [], "shortcuts": [],
               "shortcut_runs": [], "music": "off", "home": [], "home_runs": [], "focus": {}}


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
        empty = json.loads(json.dumps(EMPTY_WORLD))  # a fresh copy: its lists get appended to
        if not self.path.exists():
            return empty
        return {**empty, **json.loads(self.path.read_text(encoding="utf-8"))}

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
                  calendar: str = "", all_day: bool = False) -> dict:
        world = self._world.load()
        event = {"id": _new_id(), "title": title, "start": _iso(start), "end": _iso(end), "location": location,
                 "notes": notes, "calendar": calendar or "Home", **({"all_day": True} if all_day else {})}
        world["events"].append(event)
        self._world.save(world)
        return event

    def event(self, id: str, at: datetime | None = None) -> dict:
        return self._find(self._world.load(), id)

    def move_event(self, id: str, at: datetime | None, start: datetime, end: datetime) -> dict:
        world = self._world.load()
        event = self._find(world, id)
        event["start"], event["end"] = _iso(start), _iso(end)
        self._world.save(world)
        return event

    def delete_event(self, id: str, at: datetime | None = None) -> dict:
        world = self._world.load()
        event = self._find(world, id)
        world["events"].remove(event)
        self._world.save(world)
        return event

    @staticmethod
    def _find(world: dict, id: str) -> dict:
        found = next((e for e in world["events"] if e["id"] == id), None)
        if found is None:
            raise ToolError("I couldn't find that event any more.")
        return found


class FakeReminders:
    def __init__(self, world: World):
        self._world = world

    def list(self, query: str = "", include_done: bool = False) -> list[dict]:
        return [r for r in self._world.load()["reminders"]
                if (include_done or not r.get("done")) and (not query or _matches(r, query, "title", "notes"))]

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict:
        world = self._world.load()
        lists = list(dict.fromkeys(["Reminders"] + [r["list"] for r in world["reminders"]]))
        if list_name and list_name.casefold() not in {name.casefold() for name in lists}:
            raise ToolError(f"There's no Reminders list called “{list_name}”. There are: {', '.join(lists)}.")
        reminder = {"id": _new_id(), "title": title, "due": _iso(due), "notes": notes,
                    "list": list_name or "Reminders", "done": False}
        world["reminders"].append(reminder)
        self._world.save(world)
        return reminder

    def complete(self, id: str, done: bool = True) -> dict:
        world = self._world.load()
        for r in world["reminders"]:
            if r["id"] == id:
                r["done"] = done
                self._world.save(world)
                return r
        raise ToolError("I couldn't find that reminder.")

    def delete(self, id: str) -> dict:
        world = self._world.load()
        for r in world["reminders"]:
            if r["id"] == id:
                world["reminders"].remove(r)
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
            original = self._find(world, reply_to)
            to = to or [original["from"]]
            subject = subject or "Re: " + original["subject"]
        return self._save(world, {"id": _new_id(), "to": to, "subject": subject, "body": body, "reply_to": reply_to})

    def forward(self, id: str, to: list[str]) -> dict:
        world = self._world.load()
        original = self._find(world, id)
        return self._save(world, {"id": _new_id(), "to": to, "subject": "Fwd: " + original["subject"],
                                  "body": original["text"], "forward": id})

    @staticmethod
    def _find(world: dict, id: str) -> dict:
        original = next((m for m in world["mail"] if m["id"] == id), None)
        if original is None:
            raise ToolError("I couldn't find that in Mail any more.")
        return original

    def _save(self, world: dict, draft: dict) -> dict:
        world["drafts"].append(draft)
        self._world.save(world)
        return {"draft": True, "sent": False, "subject": draft["subject"], "to": draft["to"],
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

    def delete(self, id: str) -> dict:
        world = self._world.load()
        for n in world["notes"]:
            if n["id"] == id:
                world["notes"].remove(n)
                world.setdefault("deleted_notes", []).append(n)  # like Notes' Recently Deleted
                self._world.save(world)
                return {"id": id, "title": n["title"], "deleted": True}
        raise ToolError("I couldn't find that note.")


class FakeMusic:
    """A player whose state is `music` in world.json: "playing", "paused" or "off". Skips count in `skipped`."""

    def __init__(self, world: World):
        self._world = world

    def state(self) -> str:
        return str(self._world.load()["music"])

    def control(self, do: str) -> str:
        world = self._world.load()
        if do in ("play", "pause"):
            world["music"] = "playing" if do == "play" else "paused"
        elif do in ("next", "previous"):
            world["skipped"] = world.get("skipped", 0) + (1 if do == "next" else -1)
            world["music"] = "playing"
        else:
            raise ToolError(f"The player can't {do}.")
        self._world.save(world)
        return world["music"]


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


class FakeHome:
    """A home whose devices are `home` in world.json, each {id, name, kind, room?, state?, level?, does?, members?}.
    Every act goes into `home_runs` and changes the device's state as a real home would."""

    name = "Fake home"
    setup = "home_assistant"

    def __init__(self, world: World):
        self._world = world

    def devices(self) -> list[Device]:
        return [_fake_device(d) for d in self._world.load()["home"]]

    def act(self, id: str, do: str, value: str = "") -> Device | None:
        world = self._world.load()
        found = next((d for d in world["home"] if d["id"] == id), None)
        if found is None:
            raise ToolError("Home Assistant doesn't know that one.")
        world["home_runs"].append({"id": id, "do": do, "value": value})
        state = {"on": "on", "off": "off", "open": "open", "close": "closed", "lock": "locked",
                 "unlock": "unlocked", "disarm": "disarmed", "arm": f"armed_{value or 'away'}"}.get(do)
        if do == "toggle":
            state = "off" if found.get("state") == "on" else "on"
        elif do == "set":
            found["level"] = float(value)
            state = "on" if found.get("kind") in ("light", "fan") else found.get("state")
        elif do == "mode":
            state = value
        elif do == "run":
            for member in world["home"]:
                if member["id"] in found.get("members", []):
                    member["state"] = "on"
        if state is not None:
            found["state"] = state
        self._world.save(world)
        return _fake_device(found)


def _fake_device(d: dict) -> Device:
    return Device(d["id"], d["name"], d.get("kind", "switch"), room=d.get("room", ""), state=d.get("state", ""),
                  level=d.get("level"), does=tuple(d.get("does") or _FAKE_DOES.get(d.get("kind", ""), ("on", "off"))),
                  members=tuple(d.get("members", [])), known=d.get("known", True))


_FAKE_DOES = {"light": ("on", "off", "toggle", "set"), "scene": ("run",), "climate": ("on", "off", "set", "mode"),
              "cover": ("open", "close", "set"), "garage": ("open", "close"), "lock": ("lock", "unlock"),
              "alarm": ("arm", "disarm")}


class FakeFocus:
    """Focus modes as `focus` in world.json, name -> on. `focus_missing` true: no shortcut yet, so `set` raises
    NotSetUp and `offer` counts in `focus_offers`."""

    def __init__(self, world: World):
        self._world = world

    def set(self, on: bool, name: str = "") -> None:
        world = self._world.load()
        if world.get("focus_missing"):
            raise NotSetUp("There's no shortcut for that Focus.")
        world["focus"][name or "Do Not Disturb"] = on
        self._world.save(world)

    def offer(self, name: str = "") -> bool:
        world = self._world.load()
        world["focus_offers"] = world.get("focus_offers", 0) + 1
        self._world.save(world)
        return not name


class FakeFiles:
    """Files under the fake home, found by name and by content like Spotlight would."""

    def __init__(self, world: World, protected: Protected | None = None):
        self.scope = world.home
        self.protected = protected

    def find(self, name: str, limit: int = 20) -> list[dict]:
        return _files.newest([p for p in self._all() if name.lower() in p.name.lower()], self.scope, limit, self.protected)

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
        return _files.newest(hits, self.scope, limit, self.protected)

    def read(self, path: str, max_chars: int = 20000) -> dict:
        return _files.read(_files.checked(path, self.scope, self.protected), max_chars)

    def list(self, folder: str, name: str = "", limit: int = 20) -> list[dict]:
        return _files.listing(folder, self.scope, name, limit, self.protected)

    def move(self, paths: list[str], folder: str) -> dict:
        return _files.move(paths, folder, self.scope, self.protected)

    def _all(self) -> list[Path]:
        if not self.scope.is_dir():
            return []
        return [p for p in self.scope.rglob("*") if p.is_file() and _files.allowed(p, self.scope, protected=self.protected)]


@CONNECTIONS.register("fake")
def _fake(options: Mapping[str, Any], ctx: AdapterContext) -> Connections:
    o = options_from(FakeOptions, options, "connections.fake")
    world = World(Path(o.dir).expanduser() if o.dir else ctx.home / "fake")
    return Connections(calendar=FakeCalendar(world), reminders=FakeReminders(world), mail=FakeMail(world),
                       notes=FakeNotes(world), shortcuts=FakeShortcuts(world),
                       files=FakeFiles(world, Protected(ctx.home)), music=FakeMusic(world), home=FakeHome(world),
                       focus=FakeFocus(world))
