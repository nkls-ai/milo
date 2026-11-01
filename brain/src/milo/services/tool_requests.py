from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any, Protocol

from milo.core.packages import install as package_install
from milo.core.ports import ReminderBook
from milo.core.times import local
from milo.core.types import AppRef, ChannelError, Scope
from milo.core.wording import question, when
from milo.core.words import say

from .access import AccessGate
from .app_bridge import AppBridge, AppError
from .approvals import INSTALL, PARKED, Approvals, Parked
from .decisions import Decisions
from .installs import Installer
from .memory_requests import MemoryRequests
from .sharing import NotShareable
from .undo import Undo

log = logging.getLogger("milo.tool_requests")

# Op -> (the connection switch it needs, the kind of action it is).
APP_OPS: dict[str, tuple[str, str]] = {
    "calendar.events": ("calendar", "read"),
    "calendar.add_event": ("calendar", "change"),
    "calendar.event": ("calendar", "read"),
    "calendar.update_event": ("calendar", "change"),
    "calendar.delete_event": ("calendar", "delete"),  # the calendar has no trash: for good, so it asks (ADR 0023)
    "reminders.list": ("reminders", "read"),
    "reminders.add": ("reminders", "change"),
    "reminders.complete": ("reminders", "change"),
    "reminders.delete": ("reminders", "delete"),
}
APPS = {"calendar": AppRef("Calendar", "com.apple.iCal"), "reminders": AppRef("Reminders", "com.apple.reminders")}
# The apps an `approve` may name: the ones Milo's connection tools change things in (connect/server.py APPS).
# Anything else gets no scope, so a caller can't borrow the Allow (or Allow always) of an app it doesn't work in.
APPROVE_APPS = {"Notes": AppRef("Notes", "com.apple.Notes"), "Finder": AppRef("Finder", "com.apple.finder")}
# The apps the connection tools script (adapters/connect, `controls`): the only ones `access` checks.
ACCESS_APPS = {"Mail": AppRef("Mail"), "Notes": AppRef("Notes")}
REFUSED = {"no": "The user said no.", "timeout": "The user didn't answer, so it wasn't done.",
           "refused": "Milo isn't allowed to do this.", "parked": PARKED}


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
    - `undo.point` {path, task?}: copy a file before a task changes it, so Undo can put it back (ADR 0026). `undo.note`
      {text, task?}: how something was before the task changed it, where no copy can be kept. Result: {note}.
    - `reminder.add` {when, text}: one of Milo's own reminders, a line in reminders.md, which the worker can't
      write (ADR 0020). Always asks, with the reminder on its own marked line. Result: {reminder, due}.
    - `package.install` {manager, package}: install a program with a package manager (core/packages.py), which the
      worker's sandbox can't. An `install`: in auto mode it asks unless the user's own words for the task named the
      package (HelperQuestions.approve_install). Result: {installed, output} or {running} (services/installs.py).
    - `access` {app}: whether the system lets Milo control `app` (Mail or Notes, ACCESS_APPS), asked before a
      connection tool's first script there, so the system's question never comes as a surprise (ADR 0025).
      Result: {allowed, error?}.
    """

    def __init__(self, approvals: Approvals, bridge: AppBridge, enabled: Collection[str] = ("calendar", "reminders"),
                 memory: MemoryRequests | None = None, phone: Phone | None = None,
                 reminders: ReminderBook | None = None, access: AccessGate | None = None,
                 undo: Undo | None = None, installer: Installer | None = None, decisions: Decisions | None = None):
        self._approvals = approvals
        self._bridge = bridge
        self._enabled = frozenset(enabled)
        self._memory = memory
        """`memory.*` ops: the worker's memory tools (services/memory_requests.py). None: memory is off."""
        self._phone = phone
        self._reminders = reminders
        self._access = access
        self._undo = undo
        self._installer = installer
        self._decisions = decisions

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
                case "access":
                    if self._access is None:
                        return _ok({"allowed": True})  # nothing to check with: the script finds out, as before
                    app = ACCESS_APPS.get(str(request.get("app") or "").strip())
                    if app is None:  # only the apps the connection tools script: no caller starts any other
                        return _error("access is only for the apps Milo's connection tools control.")
                    allowed, error = await self._access.allows(app)
                    return _ok({"allowed": True} if allowed else {"allowed": False, "error": error})
                case "undo.point" | "undo.note" if self._undo is not None:
                    return await self._undo_request(op, request)
                case "reminder.add" if self._reminders is not None:
                    return await self._remind(request)
                case "package.install" if self._installer is not None:
                    return await self._install(request)
                case "classify" if self._decisions is not None:
                    return await self._classify(request)
                case str() if op.startswith("memory.") and self._memory is not None:
                    return await self._memory.handle(op, request)
        except Parked as e:
            return _error(str(e))
        except (AppError, NotShareable, ChannelError) as e:
            return _error(str(e))
        except KeyError as e:
            return _error(f"{op} needs {e}")
        except Exception:
            log.exception("tool request %s failed", op)
            return _error("Something went wrong inside Milo.")
        return _error(f"unknown op {op!r}")

    async def _undo_request(self, op: str, request: dict) -> dict:
        task = str(request.get("task") or "")
        try:
            if op == "undo.point":
                return _ok({"note": await self._undo.keep_file(task, str(request["path"]))})
            return _ok({"note": self._undo.note(task, str(request["text"]))})
        except (ValueError, OSError) as e:
            return _error(str(e))

    async def _install(self, request: dict) -> dict:
        try:
            wanted = package_install(str(request.get("manager") or ""), str(request.get("package") or ""))
        except ValueError as e:
            return _error(str(e))
        question = say("connect.install_package", package=wanted.package, manager=wanted.label)
        approve_install = getattr(self._approvals, "approve_install", None)  # HelperQuestions knows whose words
        decision = (await approve_install(wanted, question) if approve_install is not None
                    else await self._approvals.approve(INSTALL, question, careful=True))
        if not decision.allowed:
            return _error(REFUSED.get(decision.answer, REFUSED["refused"]))
        try:
            return _ok(await self._installer.run(wanted))
        except ValueError as e:
            return _error(str(e))

    async def _classify(self, request: dict) -> dict:
        """The helpers' `classify` tool: reads only, so it asks nobody (ADR 0040)."""
        items, classes = request.get("items"), request.get("classes")
        if not isinstance(items, list) or not isinstance(classes, dict):
            return _error("classify needs items (a list of texts) and classes (name -> what belongs there).")
        try:
            return _ok(await self._decisions.classify([str(i) for i in items], classes,
                                                      str(request.get("question") or "")))
        except ValueError as e:
            return _error(str(e))

    async def _remind(self, request: dict) -> dict:
        text = " ".join(str(request.get("text") or "").split())[:200]
        if not text:
            return _error("say what to remind the user of (text)")
        try:
            due = local(str(request.get("when") or "")).replace(second=0, microsecond=0)
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
