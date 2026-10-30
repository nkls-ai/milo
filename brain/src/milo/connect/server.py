from __future__ import annotations

import logging
from typing import Any

from milo.core.ports import Connections
from milo.core.types import ToolError
from milo.transport.tool_client import BrainClient, refusal

from .mcp import McpServer
from .tools import INSTRUCTIONS, Tool, by_name

log = logging.getLogger("milo.connect")

VERSION = "0.1.0"


class Toolbox:
    """Runs a tool after its approval. A connection that asks the brain itself (Calendar and Reminders
    through Milo.app, where the brain applies the level) has `approves_itself` set."""

    def __init__(self, connections: Connections, brain: BrainClient):
        self._connections = connections
        self._brain = brain
        self.tools = by_name(connections)

    def call(self, name: str, args: dict) -> Any:
        tool = self.tools[name]
        backend = getattr(self._connections, tool.connection)
        if not getattr(backend, "approves_itself", False):
            decision = self._brain.approve(tool.kind, tool.question(args))
            if not decision.allowed:
                raise ToolError(refusal(decision))
        log.info("%s: %s", tool.connection, name)
        return tool.run(backend, args)


def listing(tool: Tool) -> dict:
    read_only = tool.kind == "read"
    return {"name": tool.name, "description": tool.description, "inputSchema": tool.schema(),
            "annotations": {"readOnlyHint": read_only, "destructiveHint": False, "openWorldHint": False}}


def mcp_server(toolbox: Toolbox) -> McpServer:
    return McpServer("milo", VERSION, [listing(t) for t in toolbox.tools.values()], toolbox.call, INSTRUCTIONS)
