"""The worker's memory tools, answered by the brain over the tool socket (ops `memory.search`, `memory.remember`,
`memory.forget`). The brain holds the index and the embedder, so the MCP server needs neither.

The worker reads mail, files and web pages, so text it wants remembered may come from anyone: remembering and
forgetting always ask the user first (ADR 0010). The question is written here from the fact itself, never taken
from the caller.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from milo.core.logtext import private
from milo.core.memory import TOPICS

from .approvals import Approvals
from .memory import Memory

log = logging.getLogger("milo.memory")

MAX_LIMIT = 30


class MemoryRequests:
    def __init__(self, memory: Memory, approvals: Approvals, remember: Callable[..., object]):
        self._memory = memory
        self._approvals = approvals
        self._remember = remember
        """FactProfile.remember(text, topic=, source=, by=): adds a fact and writes profile.md."""

    async def handle(self, op: str, request: dict) -> dict:
        match op:
            case "memory.search":
                query = _text(request, "query")
                if not query:
                    return _error("say what to look for (query)")
                limit = _limit(request.get("limit"))
                return _ok({"results": await self._memory.search(query, limit)})
            case "memory.remember":
                text = _text(request, "text")
                if not text:
                    return _error("say what to remember (text)")
                topic = _text(request, "topic")
                if topic and topic not in TOPICS:
                    return _error(f"topic must be one of {', '.join(TOPICS)}")
                if not await self._approvals.confirm(f"Should I remember this: {text}?"):
                    return _error("The user said no, so it isn't remembered.")
                fact = self._remember(text, topic=topic, source="worker", by="worker")
                log.info("the worker remembered %s", private(text))
                return _ok({"remembered": text, "id": getattr(fact, "id", None)} if fact else
                           {"remembered": text, "note": "Milo already knew that."})
            case "memory.forget":
                id = _text(request, "id")
                what = self._memory.describe(id) if id else None
                if what is None:
                    return _error("There is nothing with that id. Use memory_search to find it.")
                if not await self._approvals.confirm(f"Should I forget this: {what}?"):
                    return _error("The user said no, so it stays.")
                self._memory.forget(id, "the user asked", by="worker")
                return _ok({"forgotten": what})
        return _error(f"unknown op {op!r}")


def _text(request: dict, key: str) -> str:
    return " ".join(str(request.get(key) or "").split())[:300]


def _limit(value) -> int:
    try:
        return max(1, min(MAX_LIMIT, int(value or 10)))
    except (TypeError, ValueError):
        return 10


def _ok(result) -> dict:
    return {"ok": True, "result": result}


def _error(message: str) -> dict:
    return {"ok": False, "error": message}
