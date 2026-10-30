from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from milo.core.types import HandsError

from .unix_socket import claim_socket, same_user

log = logging.getLogger("milo.hands_socket")

HandsCall = Callable[[str, object], Awaitable[object]]
"""(tool, args) -> an object with `text` and `image`. Raises HandsError."""

MAX_LINE = 1024 * 1024


class HandsSocketServer:
    """The hands socket the milo-mac MCP server talks to. JSON lines, one request and one answer each.

    Same rules as the brain socket: 0600 in a 0700 directory, peers of another user are refused.
    Requests on one connection are answered in order. Protocol: milo.core.hands.
    """

    def __init__(self, path: Path, call: HandsCall):
        self.path = path
        self._call = call
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        claim_socket(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        old_umask = os.umask(0o177)
        try:
            self._server = await asyncio.start_unix_server(self._client, path=str(self.path), limit=MAX_LINE)
        finally:
            os.umask(old_umask)
        log.info("hands listening on %s", self.path)

    async def close(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.close()
        await server.wait_closed()
        self.path.unlink(missing_ok=True)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if not same_user(writer.get_extra_info("socket")):
            log.warning("refusing a hands connection from another user")
            writer.close()
            return
        try:
            while True:
                try:
                    line = await reader.readline()
                except ValueError:
                    log.warning("dropping an over-long hands request")
                    break
                if not line:
                    break
                if not line.strip():
                    continue
                writer.write((json.dumps(await self.answer(line), ensure_ascii=False) + "\n").encode())
                await writer.drain()
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def answer(self, line: bytes) -> dict:
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or not isinstance(request.get("tool"), str):
                raise ValueError("a request needs a tool")
        except (ValueError, RecursionError) as e:
            return {"id": None, "ok": False, "error": f"bad request: {e}"}
        id = request.get("id")
        try:
            out = await self._call(request["tool"], request.get("args") or {})
        except HandsError as e:
            return {"id": id, "ok": False, "error": str(e)}
        except Exception:
            log.exception("hands call %s crashed", request["tool"])
            return {"id": id, "ok": False, "error": "Milo hit an internal error. Check ~/Milo/logs/brain.log."}
        return {"id": id, "ok": True, "text": out.text, "image": out.image}
