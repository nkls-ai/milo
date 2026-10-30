from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import struct
import sys
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path

from milo.core.events import Command, Event, Level, parse_command

log = logging.getLogger("milo.transport")

CommandHandler = Callable[[Command], Awaitable[None]]
ConnectHandler = Callable[[], Iterable[Event]]
DisconnectHandler = Callable[[], None]

SOFT_LIMIT = 256 * 1024
"""Bytes queued for an app that isn't reading: past this, loudness levels for it are dropped."""
HARD_LIMIT = 8 * 1024 * 1024
"""Past this the app is hung: its connection is closed. When it reads again it reconnects and gets a greeting."""


class UnixSocketServer:
    """JSON lines over a Unix socket. As an EventSink it broadcasts every event to every connected app.

    `on_connect` returns the events a new client needs to draw the current state; they go to that
    client only. `on_disconnect` runs when the last client hangs up. Commands from one client are handled
    in order.
    """

    def __init__(self, path: Path, on_command: CommandHandler, on_connect: ConnectHandler,
                 on_disconnect: DisconnectHandler = lambda: None, *, soft_limit: int = SOFT_LIMIT,
                 hard_limit: int = HARD_LIMIT):
        self.path = path
        self._soft_limit = soft_limit
        self._hard_limit = hard_limit
        self._on_command = on_command
        self._on_connect = on_connect
        self._on_disconnect = on_disconnect
        self._clients: set[asyncio.StreamWriter] = set()
        self._ids: dict[asyncio.StreamWriter, int] = {}
        self._next_id = 0
        self._server: asyncio.Server | None = None
        self.on_client_gone: list[Callable[[int], None]] = []
        """Called with a connection id when that app hangs up, so requests sent to it fail at once."""

    def connected(self) -> bool:
        """Some app is connected and would see an event."""
        return any(not w.is_closing() for w in self._clients)

    def emit(self, event: Event) -> None:
        """Queue `event` for every app. An app that stops reading gets no more levels once SOFT_LIMIT bytes
        wait for it (they are only a meter, and the next state resets it), and is cut off at HARD_LIMIT."""
        line = _encode(event)
        for writer in list(self._clients):
            if writer.is_closing():
                self._clients.discard(writer)
                continue
            queued = writer.transport.get_write_buffer_size()
            if queued + len(line) > self._hard_limit:
                log.warning("the app stopped reading (%d KB waiting); closing its connection", queued // 1024)
                self._clients.discard(writer)
                writer.transport.abort()
                continue
            if isinstance(event, Level) and queued > self._soft_limit:
                continue
            try:
                writer.write(line)
            except (ConnectionError, RuntimeError):
                self._clients.discard(writer)

    def request(self, event: Event) -> int | None:
        """AppLink: send `event` to the newest connected app only. Its connection id, or None if there is none.
        An older connection is usually an app on its way out (a restart) or a second copy that shouldn't act."""
        live = [w for w in self._clients if not w.is_closing()]
        if not live:
            return None
        writer = max(live, key=lambda w: self._ids[w])
        try:
            writer.write(_encode(event))
        except (ConnectionError, RuntimeError):
            return None
        return self._ids[writer]

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
        if not same_user(writer.get_extra_info("socket")):
            log.warning("refusing a connection from another user")
            writer.close()
            return
        try:
            for event in self._on_connect():
                writer.write(_encode(event))
            self._next_id += 1
            self._ids[writer] = self._next_id
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
            id = self._ids.pop(writer, None)
            writer.close()
            if self._server is not None and id is not None:
                for gone in self.on_client_gone:
                    try:
                        gone(id)
                    except Exception:
                        log.exception("handling an app's disconnect failed")
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


def same_user(sock: socket.socket | None) -> bool:
    """Whether the process on the other end runs as this user. On macOS LOCAL_PEERCRED always answers, so
    no answer is refused there; elsewhere the 0700 run/ folder is the check."""
    uid = peer_uid(sock)
    return uid == os.getuid() if uid is not None or sys.platform == "darwin" else True


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
