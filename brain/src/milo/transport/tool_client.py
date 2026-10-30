from __future__ import annotations

import itertools
import json
import socket
from pathlib import Path
from typing import Any

from milo.core.types import ActionLevel, Decision, ToolError

ANSWER_TIMEOUT_S = 3700.0  # longer than any question, even one sent to the phone: the brain answers "timeout" itself
NO_BRAIN = "Milo's brain isn't running, so I can't ask you first."
REFUSED = {"no": "The user said no. Don't do it another way.",
           "timeout": "The user didn't answer, so it wasn't done. Don't do it another way.",
           "refused": "Milo isn't allowed to do this, not even when asked."}


class BrainClient:
    """Requests to the brain's tool socket: approvals, and Calendar and Reminders work through Milo.app."""

    def __init__(self, path: Path, timeout_s: float = ANSWER_TIMEOUT_S):
        self.path = path
        self.timeout_s = timeout_s
        self._ids = itertools.count(1)

    def request(self, body: dict) -> Any:
        """The result of one request. Raises ToolError with the brain's plain-language error."""
        id = next(self._ids)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(self.timeout_s)
                s.connect(str(self.path))
                s.sendall((json.dumps({"id": id, **body}) + "\n").encode())
                answer = json.loads(s.makefile("rb").readline() or b"{}")
        except (OSError, ValueError):
            raise ToolError(NO_BRAIN) from None
        if not answer.get("ok"):
            raise ToolError(str(answer.get("error") or "Milo couldn't do that."))
        return answer.get("result")

    def approve(self, kind: str, summary: str, app: str = "") -> Decision:
        """The brain applies the user's action levels and asks if needed. `app`: the app a change happens in, so
        an Allow covers the next change there. Without a brain only reading goes."""
        try:
            r = self.request({"op": "approve", "kind": kind, "summary": summary, **({"app": app} if app else {})})
        except ToolError:
            if kind == "read":
                return Decision(True, ActionLevel.READ, "auto")
            raise
        return Decision(bool(r.get("allowed")), ActionLevel(r.get("level", "ask_first")), str(r.get("answer", "")))


def refusal(decision: Decision) -> str:
    return REFUSED.get(decision.answer, REFUSED["refused"])
