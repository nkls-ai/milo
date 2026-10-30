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
        unknown = sorted(set(args) - set(tool.properties))
        if unknown:
            raise ToolError(f"{name} doesn't take {', '.join(unknown)}")
        if not getattr(backend, "approves_itself", False):
            facts = tool.about(backend, args) if tool.about and tool.kind != "read" else {}
            decision = self._brain.approve(tool.kind, tool.question({**args, **facts}))
            if not decision.allowed:
                raise ToolError(refusal(decision))
        log.info("%s: %s", tool.connection, name)
        return tool.run(backend, args)


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
            "annotations": {"readOnlyHint": read_only, "destructiveHint": False, "openWorldHint": False}}


def mcp_server(toolbox: Toolbox) -> McpServer:
    return McpServer("milo", VERSION, [listing(t) for t in toolbox.tools.values()], toolbox.call, INSTRUCTIONS)
