from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from milo import system

from .unix_socket import claim_socket, same_user

log = logging.getLogger("milo.transport.tools")

MAX_IN_FLIGHT = 4
"""Requests one connection may have waiting at once. Each question queues behind the one before it, so a
helper in a loop could otherwise line up questions without end."""
MAX_IN_FLIGHT_ALL = 16
"""And across every connection, so hanging up and dialling again doesn't make room."""
BUSY = "Too many requests at once. Wait for the answers to the ones you sent, then try again."

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
        await asyncio.to_thread(claim_socket, self.path)
        self._server = await system.start_local_server(self._client, self.path, limit=MAX_LINE)
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
        mine: set[asyncio.Task] = set()
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
                    busy = len(mine) >= MAX_IN_FLIGHT or len(self._running) >= MAX_IN_FLIGHT_ALL
                    task = asyncio.create_task(self._answer(line, writer, busy=busy))
                    for running in (self._running, mine):
                        running.add(task)
                        task.add_done_callback(running.discard)
        except ConnectionError:
            pass
        finally:
            for task in mine:  # nobody is left to answer: a question it asked goes away too
                task.cancel()
            writer.close()

    async def _answer(self, line: bytes, writer: asyncio.StreamWriter, *, busy: bool = False) -> None:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("not an object")
        except (ValueError, RecursionError) as e:
            log.warning("dropping a bad tool request: %s", e)
            return
        if busy:
            log.warning("a tool connection has %d requests waiting; refusing %s", MAX_IN_FLIGHT, request.get("op"))
            answer = {"id": request.get("id"), "ok": False, "error": BUSY}
        else:
            answer = {"id": request.get("id"), **await self._handler(request)}
        try:
            writer.write((json.dumps(answer, ensure_ascii=False, default=str) + "\n").encode())
            await writer.drain()
        except (ConnectionError, RuntimeError):
            pass
