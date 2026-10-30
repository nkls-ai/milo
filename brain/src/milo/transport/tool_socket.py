from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path

from .unix_socket import claim_socket, same_user

log = logging.getLogger("milo.transport.tools")

RequestHandler = Callable[[dict], Awaitable[dict]]
MAX_LINE = 1024 * 1024


class ToolSocketServer:
    """Requests and answers as JSON lines over a 0600 Unix socket, for Milo's own helper processes.

    Each request is an object with an `id`; the answer carries the same `id` plus whatever the handler
    returned. Requests on one connection run concurrently, since a question to the user can take a minute.
    """

    def __init__(self, path: Path, handler: RequestHandler):
        self.path = path
        self._handler = handler
        self._server: asyncio.Server | None = None
        self._running: set[asyncio.Task] = set()

    async def start(self) -> None:
        claim_socket(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        old_umask = os.umask(0o177)
        try:
            self._server = await asyncio.start_unix_server(self._client, path=str(self.path), limit=MAX_LINE)
        finally:
            os.umask(old_umask)
        log.info("tool socket on %s", self.path)

    async def close(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.close()
        for task in list(self._running):
            task.cancel()
        await server.wait_closed()
        self.path.unlink(missing_ok=True)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if not same_user(writer.get_extra_info("socket")):
            log.warning("refusing a tool connection from another user")
            writer.close()
            return
        try:
            while True:
                try:
                    line = await reader.readline()
                except ValueError:
                    log.warning("dropping an over-long tool request")
                    break
                if not line:
                    break
                if line.strip():
                    task = asyncio.create_task(self._answer(line, writer))
                    self._running.add(task)
                    task.add_done_callback(self._running.discard)
        except ConnectionError:
            pass
        finally:
            writer.close()

    async def _answer(self, line: bytes, writer: asyncio.StreamWriter) -> None:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("not an object")
        except (ValueError, RecursionError) as e:
            log.warning("dropping a bad tool request: %s", e)
            return
        answer = {"id": request.get("id"), **await self._handler(request)}
        try:
            writer.write((json.dumps(answer, ensure_ascii=False, default=str) + "\n").encode())
            await writer.drain()
        except (ConnectionError, RuntimeError):
            pass
