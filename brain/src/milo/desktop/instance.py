"""One desktop per Milo home, with a fixed local activation message.

The kernel lock owns the application lifetime; the Qt local server only wakes
the existing window. An endpoint is reclaimed only after acquiring that lock.
"""
from __future__ import annotations

import getpass
import hashlib
import os
from pathlib import Path
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from milo.transport.instance_lock import AlreadyRunning, acquire


def server_name(home: Path) -> str:
    canonical = os.path.normcase(str(home.expanduser().resolve()))
    user = str(os.getuid()) if hasattr(os, "getuid") else getpass.getuser().casefold()
    digest = hashlib.sha256(f"{user}\0{canonical}".encode()).hexdigest()[:40]
    return f"milo-desktop-{digest}"


class DesktopInstance(QObject):
    activation_requested = Signal()

    def __init__(self, home: Path, parent=None, *, activation_timeout_s: float = 2.0):
        super().__init__(parent)
        self.home = home.expanduser().resolve()
        self.name = server_name(self.home)
        self.activation_delivered = False
        self._timeout_s = max(0., min(5., activation_timeout_s))
        self._fd: int | None = None
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.setMaxPendingConnections(8)
        self._server.newConnection.connect(self._accept)
        self._clients: set[QLocalSocket] = set()

    def start(self) -> bool:
        """Own this desktop, or notify its current owner and return False.

        False always means another process owns the lock, including a process
        still starting or temporarily unable to acknowledge activation.
        """
        if self._fd is not None:
            return True
        try:
            self._fd = acquire(self.home / "run" / "desktop.lock")
        except AlreadyRunning:
            self.activation_delivered = self._activate_owner()
            return False
        try:
            os.set_inheritable(self._fd, False)
            QLocalServer.removeServer(self.name)
            if not self._server.listen(self.name):
                raise RuntimeError(f"Couldn't start Milo's local desktop activation: {self._server.errorString()}")
        except BaseException:
            self.close()
            raise
        return True

    def _activate_owner(self) -> bool:
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            socket = QLocalSocket()
            try:
                socket.connectToServer(self.name)
                remaining_ms = max(1, round((deadline - time.monotonic()) * 1000))
                if socket.waitForConnected(min(75, remaining_ms)):
                    socket.write(b"show\n")
                    socket.flush()
                    reply = bytearray()
                    while time.monotonic() < deadline:
                        reply.extend(bytes(socket.readAll()))
                        if reply == b"ok\n":
                            return True
                        if len(reply) > 3:
                            break
                        if socket.state() == QLocalSocket.LocalSocketState.UnconnectedState:
                            break
                        remaining_ms = max(1, round((deadline - time.monotonic()) * 1000))
                        socket.waitForReadyRead(min(75, remaining_ms))
            finally:
                socket.abort()
            if time.monotonic() < deadline:
                time.sleep(min(.025, deadline - time.monotonic()))
        return False

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if len(self._clients) >= 8:
                socket.abort()
                socket.deleteLater()
                continue
            self._clients.add(socket)
            socket.setReadBufferSize(16)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.setInterval(1000)
            # abort() is not a Qt slot. Connecting its bound C++ method asks
            # PySide to create a dynamic meta-method which can outlive the
            # Python wrapper during deferred deletion. Keep a Python callback
            # (and its socket wrapper) alive until the parented timer is gone.
            timer.timeout.connect(lambda client=socket: client.abort())
            timer.start()
            buffer = bytearray()

            def read(client=socket, data=buffer):
                data.extend(bytes(client.readAll()))
                if bytes(data) == b"show\n":
                    self.activation_requested.emit()
                    client.write(b"ok\n")
                    client.flush()
                    client.disconnectFromServer()
                elif not b"show\n".startswith(data):
                    client.abort()

            def discard(client=socket, timeout=timer):
                timeout.stop()
                self._clients.discard(client)
                client.deleteLater()

            socket.readyRead.connect(read)
            socket.disconnected.connect(discard)
            if socket.bytesAvailable():
                read()

    def close(self) -> None:
        for client in list(self._clients):
            client.abort()
            client.deleteLater()
        self._clients.clear()
        self._server.close()
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
