from __future__ import annotations

import logging
from typing import Any

from milo.core.ports import Connections, connection_identity
from milo.core.types import ToolError
from milo.transport.tool_client import BrainClient, refusal

from .brief import OWN
from .mcp import McpServer
from .memory_tools import MEMORY_TOOLS, RemoteMemory
from .milo_tools import MILO_TOOLS, RemoteMilo
from .tools import Tool, by_name

log = logging.getLogger("milo.connect")

VERSION = "0.1.0"


# Kinds that can't be undone (ADR 0023), for the MCP destructiveHint.
DESTRUCTIVE = ("delete", "discard", "overwrite_file")


class Toolbox:
    """Runs a tool after its approval. A connection that asks the brain itself (Calendar and Reminders
    through Milo.app, where the brain applies the level) has `approves_itself` set. `kinds` limits it to the
    connections a helper's task needs (core/task_scope.py); Milo's own tools are always there."""

    def __init__(self, connections: Connections, brain: BrainClient, memory: RemoteMemory | None = None,
                 milo: RemoteMilo | None = None, *, kinds: frozenset[str] | None = None):
        self._connections = connections
        self._brain = brain
        self._memory = memory
        self._milo = milo
        self._allowed: set[str] = set()
        """Apps the system lets Milo control, as the brain found before the first script there."""
        tools = (by_name(connections) | ({t.name: t for t in MEMORY_TOOLS} if memory is not None else {})
                 | ({t.name: t for t in MILO_TOOLS} if milo is not None else {}))
        self.tools = {name: t for name, t in tools.items()
                      if kinds is None or t.connection == OWN or t.connection in kinds}

    def call(self, name: str, args: dict) -> Any:
        tool = self.tools[name]
        own = {"memory": self._memory, "milo": self._milo, "install": self._milo}
        backend = own[tool.connection] if tool.connection in own else getattr(self._connections, tool.connection)
        unknown = sorted(set(args) - set(tool.properties))
        if unknown:
            raise ToolError(f"{name} doesn't take {', '.join(unknown)}")
        if not getattr(backend, "approves_itself", False):
            facts = tool.about(backend, args) if tool.about and tool.kind != "read" else {}
            identity = connection_identity(backend, tool.connection.capitalize())
            decision = self._brain.approve(tool.kind, tool.question({**args, **facts}),
                                           app=identity.app.name if identity.app else "")
            if not decision.allowed:
                raise ToolError(refusal(decision))
        self._may_control(getattr(backend, "controls", ""))
        log.info("%s: %s", tool.connection, name)
        return tool.run(backend, args)

    def _may_control(self, app: str) -> None:
        """Before the first script in `app`, the brain checks the system lets Milo control it, and says what is
        coming if the system is about to ask the user (ADR 0025). Raises ToolError if the user said no."""
        if not app or app in self._allowed:
            return
        if self._brain.access(app):
            self._allowed.add(app)


class BrainPhone:
    """The send_to_phone tool's connection: the brain checks the file, asks the user and sends it."""

    approves_itself = True

    def __init__(self, brain: BrainClient):
        self._brain = brain

    def send(self, path: str, caption: str = "") -> dict:
        return self._brain.request({"op": "send_to_phone", "path": path, "caption": caption})


def listing(tool: Tool) -> dict:
    read_only = tool.kind == "read"
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.schema(),
            "annotations": {"readOnlyHint": read_only, "destructiveHint": tool.kind in DESTRUCTIVE,
                            "openWorldHint": False}}


def mcp_server(toolbox: Toolbox) -> McpServer:
    """No server instructions: Codex would repeat them in every tool's description. The helper's prompt carries
    them once (connect/brief.py)."""
    return McpServer("milo", VERSION, [listing(t) for t in toolbox.tools.values()], toolbox.call)
