from __future__ import annotations

import logging
from typing import Any

from .app_bridge import AppBridge, AppError
from .approvals import Approvals

log = logging.getLogger("milo.tool_requests")

APP_OPS = ("calendar.events", "calendar.add_event", "reminders.list", "reminders.add", "reminders.complete")


class ToolRequests:
    """Answers the requests that arrive on the brain's tool socket (run/tools.sock).

    Callers are Milo's own helpers: the app-connections MCP server the worker starts, and anything else
    that needs the user's yes. One JSON object per request, with an `op`:

    - `approve` {kind, summary}: the action level for `kind`, asking `summary` if it is ask_first.
      Result: {allowed, level, answer}.
    - `confirm` {summary}: always ask. Result: {yes}.
    - `app` {name, args}: run `name` (one of APP_OPS) in Milo.app. Result: what the app returned.
    """

    def __init__(self, approvals: Approvals, bridge: AppBridge):
        self._approvals = approvals
        self._bridge = bridge

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
                    args = request.get("args") or {}
                    if not isinstance(args, dict):
                        return _error("args must be an object")
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
