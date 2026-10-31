"""milo-mac: the MCP stdio server the worker CLI starts, standard library only.

It speaks just enough MCP (JSON-RPC 2.0, one message per line on stdin/stdout): initialize, ping,
tools/list and tools/call. Each tool call is forwarded to the brain's hands socket and the answer comes
back as text, plus the screenshot as an image block. All the checking happens in the brain; this process
only translates. See milo.core.hands for the tools and the socket protocol.

    python -m milo.mcp_server --socket ~/Milo/run/hands.sock
"""

from __future__ import annotations

import argparse
import base64
import itertools
import json
import socket
import sys
from pathlib import Path
from typing import IO

from milo.core.hands import SERVER_NAME, TOOLS

PROTOCOL_VERSION = "2025-06-18"
CALL_TIMEOUT_S = 120.0  # a confirm question alone may wait a minute
NO_BRAIN = "Milo's brain isn't reachable, so the Mac tools are off."


class HandsClient:
    """One request per connection to the hands socket."""

    def __init__(self, path: Path, timeout_s: float = CALL_TIMEOUT_S):
        self.path = path
        self.timeout_s = timeout_s
        self._ids = itertools.count(1)

    def call(self, tool: str, args: dict) -> dict:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout_s)
                sock.connect(str(self.path))
                sock.sendall((json.dumps({"id": next(self._ids), "tool": tool, "args": args}) + "\n").encode())
                with sock.makefile("rb") as stream:
                    line = stream.readline()
        except TimeoutError:
            return {"ok": False, "error": "Milo didn't answer in time."}
        except OSError:
            return {"ok": False, "error": NO_BRAIN}
        try:
            answer = json.loads(line)
        except ValueError:
            return {"ok": False, "error": NO_BRAIN}
        return answer if isinstance(answer, dict) else {"ok": False, "error": NO_BRAIN}


def tool_result(answer: dict) -> dict:
    """A hands socket answer as an MCP CallToolResult."""
    if not answer.get("ok"):
        return {"content": [{"type": "text", "text": str(answer.get("error") or "failed")}], "isError": True}
    content: list[dict] = [{"type": "text", "text": str(answer.get("text") or "Done.")}]
    image = str(answer.get("image") or "")
    if image:
        try:
            data = base64.b64encode(Path(image).read_bytes()).decode()
            content.append({"type": "image", "data": data, "mimeType": "image/png"})
        except OSError:
            content.append({"type": "text", "text": "(The screenshot file could not be read.)"})
    return {"content": content, "isError": False}


def handle(message: object, hands: HandsClient) -> dict | None:
    """The response to one JSON-RPC message, or None for a notification."""
    if not isinstance(message, dict):
        return _error(None, -32600, "invalid request")
    id, method = message.get("id"), message.get("method")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if id is None:
        return None
    if method == "initialize":
        # No instructions: Codex would repeat them in front of every tool's description. The screen helper's
        # prompt carries them once (milo.connect.brief).
        return _ok(id, {"protocolVersion": str(params.get("protocolVersion") or PROTOCOL_VERSION),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": SERVER_NAME, "version": "0.1.0"}})
    if method == "ping":
        return _ok(id, {})
    if method == "tools/list":
        return _ok(id, {"tools": [t.mcp() for t in TOOLS]})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(args, dict):
            return _error(id, -32602, "tools/call needs a name and an arguments object")
        return _ok(id, tool_result(hands.call(name, args)))
    return _error(id, -32601, f"unknown method {method}")


def serve(hands: HandsClient, stdin: IO[str], stdout: IO[str]) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response = _error(None, -32700, "parse error")
        else:
            response = handle(message, hands)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def _ok(id: object, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _error(id: object, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="milo-mac", description=__doc__.splitlines()[0])
    parser.add_argument("--socket", required=True, type=Path, help="the brain's hands socket")
    args = parser.parse_args(argv)
    serve(HandsClient(args.socket.expanduser()), sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
