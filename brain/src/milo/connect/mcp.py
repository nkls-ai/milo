"""The MCP stdio transport: JSON-RPC 2.0, one message per line. Just enough of the protocol for tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import IO, Any

from milo.core.types import ToolError

log = logging.getLogger("milo.connect")

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_TEXT = 60_000


class McpServer:
    """Serves `tools` (name -> (description, input schema, annotations)) and calls `call(name, args)`.

    `call` returns a JSON-ready result or raises ToolError, which goes back to the agent as a tool error
    with the plain message, so it can tell the user.
    """

    def __init__(self, name: str, version: str, tools: list[dict], call: Callable[[str, dict], Any],
                 instructions: str = ""):
        self._info = {"name": name, "version": version}
        self._tools = tools
        self._call = call
        self._instructions = instructions

    def serve(self, stdin: IO[str], stdout: IO[str]) -> None:
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self._send(stdout, {"jsonrpc": "2.0", "id": None,
                                    "error": {"code": -32700, "message": "parse error"}})
                continue
            reply = self.handle(message)
            if reply is not None:
                self._send(stdout, reply)

    def handle(self, message: object) -> dict | None:
        """The response to one message, or None for notifications."""
        if not isinstance(message, dict) or "method" not in message:
            return None  # a response to something we never ask, or junk
        id, method, params = message.get("id"), message["method"], message.get("params") or {}
        if id is None:
            return None  # notifications/initialized, notifications/cancelled, ...
        try:
            result = self._method(method, params)
        except _RpcError as e:
            return {"jsonrpc": "2.0", "id": id, "error": {"code": e.code, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": id, "result": result}

    def _method(self, method: str, params: dict) -> dict:
        match method:
            case "initialize":
                asked = params.get("protocolVersion")
                version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": self._info}
                if self._instructions:
                    result["instructions"] = self._instructions
                return result
            case "ping":
                return {}
            case "tools/list":
                return {"tools": self._tools}
            case "tools/call":
                name, args = params.get("name"), params.get("arguments") or {}
                if not isinstance(args, dict):
                    raise _RpcError(-32602, "arguments must be an object")
                if name not in {t["name"] for t in self._tools}:
                    raise _RpcError(-32602, f"unknown tool {name!r}")
                return self._tool_result(name, args)
        raise _RpcError(-32601, f"method not found: {method}")

    def _tool_result(self, name: str, args: dict) -> dict:
        try:
            result = self._call(name, args)
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception:
            log.exception("tool %s crashed", name)
            return {"content": [{"type": "text", "text": "That didn't work: something broke inside Milo."}],
                    "isError": True}
        text = json.dumps(result, ensure_ascii=False, default=str)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT] + " …(cut off)"
        return {"content": [{"type": "text", "text": text}], "isError": False}

    @staticmethod
    def _send(stdout: IO[str], message: dict) -> None:
        stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        stdout.flush()


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
