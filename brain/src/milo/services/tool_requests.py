from __future__ import annotations

import logging
from collections.abc import Collection
from datetime import datetime
from typing import Any, Protocol

from milo.core.ports import ReminderBook
from milo.core.types import AppRef, ChannelError, Scope
from milo.core.wording import question, when

from .app_bridge import AppBridge, AppError
from .approvals import Approvals
from .memory_requests import MemoryRequests
from .sharing import NotShareable
from .undo import Undo

log = logging.getLogger("milo.tool_requests")

# Op -> (the connection switch it needs, the kind of action it is).
APP_OPS: dict[str, tuple[str, str]] = {
    "calendar.events": ("calendar", "read"),
    "calendar.add_event": ("calendar", "change"),
    "reminders.list": ("reminders", "read"),
    "reminders.add": ("reminders", "change"),
    "reminders.complete": ("reminders", "change"),
}
APPS = {"calendar": AppRef("Calendar", "com.apple.iCal"), "reminders": AppRef("Reminders", "com.apple.reminders")}
# The apps an `approve` may name: the ones Milo's connection tools change things in (connect/server.py APPS).
# Anything else gets no scope, so a caller can't borrow the Allow (or Allow always) of an app it doesn't work in.
APPROVE_APPS = {"Notes": AppRef("Notes", "com.apple.Notes"), "Finder": AppRef("Finder", "com.apple.finder")}
REFUSED = {"no": "The user said no.", "timeout": "The user didn't answer, so it wasn't done.",
           "refused": "Milo isn't allowed to do this."}


class Phone(Protocol):
    """The owner's phone, for files a helper sends there (MessageService). `check` returns the file it will
    send (an Outgoing); `send_file` sends it only if it is still the same file."""

    def check(self, path: str) -> Any: ...

    def question(self, outgoing: Any) -> str: ...

    async def send_file(self, outgoing: Any, caption: str = "") -> dict: ...


NO_PHONE = "Milo can't send files to your phone: messages are switched off in Milo's settings."


class ToolRequests:
    """Answers the requests that arrive on the brain's tool socket (run/tools.sock).

    Callers are Milo's own helpers: the app-connections MCP server the worker starts, and anything else
    that needs the user's yes. One JSON object per request, with an `op`:

    - `approve` {kind, summary, app?}: the action level for `kind`, asking `summary` if it is ask_first. `app`
      names the app a change happens in, so the user's Allow can cover the next one (ADR 0022).
      Result: {allowed, level, answer}.
    - `confirm` {summary}: always ask. Result: {yes}.
    - `app` {name, args}: run `name` (one of APP_OPS) in Milo.app. Result: what the app returned.
      The app lends its Calendar and Reminders permission here, so this side checks the connection is
      switched on and applies the op's action level itself, whoever calls. The question is written here
      from the arguments that go to the app, never taken from the caller.
    - `send_to_phone` {path, caption?}: send one file to the owner's phone. Always a `share`, so it asks first
      unless the user made sharing not ask; the question names the file and its size. Result: {sent}.
    - `undo.point` {path, task?}: copy a file before a task changes it, so Undo can put it back (ADR 0024). `undo.note`
      {text, task?}: how something was before the task changed it, where no copy can be kept. Result: {note}.
    - `reminder.add` {when, text}: one of Milo's own reminders, a line in reminders.md, which the worker can't
      write (ADR 0020). Always asks, with the reminder on its own marked line. Result: {reminder, due}.
    """

    def __init__(self, approvals: Approvals, bridge: AppBridge, enabled: Collection[str] = ("calendar", "reminders"),
                 memory: MemoryRequests | None = None, phone: Phone | None = None,
                 reminders: ReminderBook | None = None, undo: Undo | None = None):
        self._approvals = approvals
        self._bridge = bridge
        self._enabled = frozenset(enabled)
        self._memory = memory
        """`memory.*` ops: the worker's memory tools (services/memory_requests.py). None: memory is off."""
        self._phone = phone
        self._reminders = reminders
        self._undo = undo

    async def handle(self, request: dict) -> dict:
        """{"ok": true, "result": ...} or {"ok": false, "error": "plain words"}. Never raises."""
        op = request.get("op")
        try:
            match op:
                case "approve":
                    app = APPROVE_APPS.get(str(request.get("app") or "").strip())
                    decision = await self._approvals.approve(str(request["kind"]), _summary(request),
                                                             scope=Scope((app,)) if app else None)
                    return _ok(decision.to_dict())
                case "confirm":
                    return _ok({"yes": await self._approvals.confirm(_summary(request))})
                case "app":
                    name = str(request["name"])
                    if name not in APP_OPS:
                        return _error(f"unknown app op {name!r}")
                    connection, kind = APP_OPS[name]
                    if connection not in self._enabled:
                        return _error(f"The {connection} connection is switched off in Milo's settings.")
                    args = request.get("args") or {}
                    if not isinstance(args, dict):
                        return _error("args must be an object")
                    decision = await self._approvals.approve(kind, question(name.replace(".", "_"), args),
                                                             scope=Scope((APPS[connection],)))
                    if not decision.allowed:
                        return _error(REFUSED.get(decision.answer, REFUSED["refused"]))
                    return _ok(await self._bridge.call(name, args))
                case "send_to_phone":
                    if self._phone is None:
                        return _error(NO_PHONE)
                    outgoing = self._phone.check(str(request["path"]))
                    decision = await self._approvals.approve("share", self._phone.question(outgoing))
                    if not decision.allowed:
                        return _error(REFUSED.get(decision.answer, REFUSED["refused"]))
                    return _ok(await self._phone.send_file(outgoing, str(request.get("caption") or "")))
                case "undo.point" | "undo.note" if self._undo is not None:
                    return self._undo_request(op, request)
                case "reminder.add" if self._reminders is not None:
                    return await self._remind(request)
                case str() if op.startswith("memory.") and self._memory is not None:
                    return await self._memory.handle(op, request)
        except (AppError, NotShareable, ChannelError) as e:
            return _error(str(e))
        except KeyError as e:
            return _error(f"{op} needs {e}")
        except Exception:
            log.exception("tool request %s failed", op)
            return _error("Something went wrong inside Milo.")
        return _error(f"unknown op {op!r}")

    def _undo_request(self, op: str, request: dict) -> dict:
        task = str(request.get("task") or "")
        try:
            if op == "undo.point":
                return _ok({"note": self._undo.keep_file(task, str(request["path"]))})
            return _ok({"note": self._undo.note(task, str(request["text"]))})
        except (ValueError, OSError) as e:
            return _error(str(e))

    async def _remind(self, request: dict) -> dict:
        text = " ".join(str(request.get("text") or "").split())[:200]
        if not text:
            return _error("say what to remind the user of (text)")
        try:
            due = datetime.fromisoformat(str(request.get("when") or "")).replace(tzinfo=None, second=0,
                                                                                 microsecond=0)
        except ValueError:
            return _error("when must look like 2026-11-05T15:00")
        if not await self._approvals.confirm(f"Should I remind you on {when(due.isoformat())}?\n› {text}"):
            return _error(REFUSED["no"])
        reminder = self._reminders.add(due, text)
        return _ok({"reminder": reminder.text, "due": f"{reminder.due:%Y-%m-%dT%H:%M}"})


def _summary(request: dict) -> str:
    summary = " ".join(str(request["summary"]).split())
    if not summary:
        raise KeyError("summary")
    return summary[:300]


def _ok(result: Any) -> dict:
    return {"ok": True, "result": result}


def _error(message: str) -> dict:
    return {"ok": False, "error": message}
