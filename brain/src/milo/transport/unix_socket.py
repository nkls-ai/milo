from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import struct
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from milo.core.events import Command, Event, parse_command

log = logging.getLogger("milo.transport")

CommandHandler = Callable[[Command], Awaitable[None]]
ConnectHandler = Callable[[], Iterable[Event]]
DisconnectHandler = Callable[[], None]


class UnixSocketServer:
    """JSON lines over a Unix socket. As an EventSink it broadcasts every event to every connected app.

    `on_connect` returns the events a new client needs to draw the current state; they go to that
    client only. `on_disconnect` runs when the last client hangs up. Commands from one client are handled
    in order.
    """

    def __init__(self, path: Path, on_command: CommandHandler, on_connect: ConnectHandler,
                 on_disconnect: DisconnectHandler = lambda: None):
        self.path = path
        self._on_command = on_command
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._clients: set[asyncio.StreamWriter] = set()
        self._server: asyncio.Server | None = None

    def connected(self) -> bool:
        """Some app is connected and would see an event."""
        return any(not w.is_closing() for w in self._clients)

    def emit(self, event: Event) -> None:
        line = _encode(event)
        for writer in list(self._clients):
            if writer.is_closing():
                self._clients.discard(writer)
                continue
            try:
                writer.write(line)
            except (ConnectionError, RuntimeError):
                self._clients.discard(writer)

    async def start(self) -> None:
        claim_socket(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        # Bind under a restrictive umask so the socket is never more open than 0600, not even briefly.
        old_umask = os.umask(0o177)
        try:
            self._server = await asyncio.start_unix_server(self._client, path=str(self.path))
        finally:
            os.umask(old_umask)
        log.info("listening on %s", self.path)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        try:
            # Not Server.serve_forever: once cancelled, it waits for every client to hang up before anything
            # closes them, so a brain stopped while the app was connected never exited.
            await asyncio.get_running_loop().create_future()
        finally:
            await self.close()

    async def close(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.close()
        for writer in list(self._clients):
            writer.close()
        self._clients.clear()
        await server.wait_closed()
        self.path.unlink(missing_ok=True)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if peer_uid(writer.get_extra_info("socket")) not in (os.getuid(), None):
            log.warning("refusing a connection from another user")
            writer.close()
            return
        try:
            for event in self._on_connect():
                writer.write(_encode(event))
            self._clients.add(writer)
            while True:
                try:
                    line = await reader.readline()
                except ValueError:
                    log.warning("dropping an over-long message")
                    continue
                if not line:
                    break
                await self._handle_line(line)
        except ConnectionError:
            pass
        finally:
            self._clients.discard(writer)
            writer.close()
            if self._server is not None and not self.connected():
                try:
                    self._on_disconnect()
                except Exception:
                    log.exception("handling the app's disconnect failed")

    async def _handle_line(self, line: bytes) -> None:
        if not line.strip():
            return
        try:
            command = parse_command(json.loads(line))
        # ValueError covers JSONDecodeError, UnicodeDecodeError and ProtocolError. Deeply nested
        # JSON raises RecursionError, which would otherwise kill the connection.
        except (ValueError, RecursionError) as e:
            log.warning("dropping bad message %r: %s", line[:80], e)
            return
        try:
            await self._on_command(command)
        except Exception:
            log.exception("handling %s failed", command.type)


def _encode(event: Event) -> bytes:
    return (json.dumps(event.to_wire(), ensure_ascii=False) + "\n").encode()


_SOL_LOCAL, _LOCAL_PEERCRED = 0, 0x001  # macOS <sys/un.h>


def peer_uid(sock: socket.socket | None) -> int | None:
    """UID of the process on the other end, or None if the OS can't tell us."""
    if sock is None:
        return None
    try:
        if hasattr(socket, "SO_PEERCRED"):  # Linux: struct ucred {pid, uid, gid}
            return struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
        cred = sock.getsockopt(_SOL_LOCAL, _LOCAL_PEERCRED, 76)  # macOS: struct xucred {version, uid, ...}
        return struct.unpack_from("=II", cred)[1]
    except OSError:
        return None


def claim_socket(path: Path) -> None:
    """Remove a stale socket, or exit if another brain is already serving on it."""
    if not path.exists():
        return
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        probe.connect(str(path))
    except OSError:
        path.unlink()
        return
    finally:
        probe.close()
    raise SystemExit(f"another Milo brain is already running on {path}")
