from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any

from .app_bridge import AppBridge, AppError
from .approvals import Approvals

log = logging.getLogger("milo.tool_requests")

# Op -> (the connection switch it needs, the kind of action it is).
APP_OPS: dict[str, tuple[str, str]] = {
    "calendar.events": ("calendar", "read"),
    "calendar.add_event": ("calendar", "change"),
    "reminders.list": ("reminders", "read"),
    "reminders.add": ("reminders", "change"),
    "reminders.complete": ("reminders", "change"),
}
REFUSED = {"no": "The user said no.", "timeout": "The user didn't answer, so it wasn't done.",
           "refused": "Milo isn't allowed to do this."}


class ToolRequests:
    """Answers the requests that arrive on the brain's tool socket (run/tools.sock).

    Callers are Milo's own helpers: the app-connections MCP server the worker starts, and anything else
    that needs the user's yes. One JSON object per request, with an `op`:

    - `approve` {kind, summary}: the action level for `kind`, asking `summary` if it is ask_first.
      Result: {allowed, level, answer}.
    - `confirm` {summary}: always ask. Result: {yes}.
    - `app` {name, args, summary}: run `name` (one of APP_OPS) in Milo.app. Result: what the app returned.
      The app lends its Calendar and Reminders permission here, so this side checks the connection is
      switched on and applies the op's action level itself (asking `summary` if needed), whoever calls.
    """

    def __init__(self, approvals: Approvals, bridge: AppBridge, enabled: Collection[str] = ("calendar", "reminders")):
        self._approvals = approvals
        self._bridge = bridge
        self._enabled = frozenset(enabled)

    async def handle(self, request: dict) -> dict:
        """{"ok": true, "result": ...} or {"ok": false, "error": "plain words"}. Never raises."""
        op = request.get("op")
        try:
            match op:
                case "approve":
                    decision = await self._approvals.approve(str(request["kind"]), _summary(request))
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
                    summary = " ".join(str(request.get("summary") or "").split())[:300] or f"Go ahead with {name}?"
                    decision = await self._approvals.approve(kind, summary)
                    if not decision.allowed:
                        return _error(REFUSED.get(decision.answer, REFUSED["refused"]))
                    return _ok(await self._bridge.call(name, args))
        except AppError as e:
            return _error(str(e))
        except KeyError as e:
            return _error(f"{op} needs {e}")
        except Exception:
            log.exception("tool request %s failed", op)
            return _error("Something went wrong inside Milo.")
        return _error(f"unknown op {op!r}")


def _summary(request: dict) -> str:
    summary = " ".join(str(request["summary"]).split())
    if not summary:
        raise KeyError("summary")
    return summary[:300]


def _ok(result: Any) -> dict:
    return {"ok": True, "result": result}


def _error(message: str) -> dict:
    return {"ok": False, "error": message}
