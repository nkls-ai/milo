"""A reconnecting JSONL client. Socket I/O never blocks the Qt event loop."""
from __future__ import annotations

import json
import queue
import socket
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from milo import system

MAX_LINE = 8 * 1024 * 1024


class BrainConnection(QThread):
    event = Signal(dict)
    connection_changed = Signal(bool)
    status = Signal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path
        self._stop = threading.Event()
        self._guard = threading.Lock()
        self._socket: socket.socket | None = None
        self._outbox: queue.Queue[tuple[socket.socket, bytes] | None] = queue.Queue(maxsize=256)

    @property
    def connected(self) -> bool:
        with self._guard:
            return self._socket is not None

    def send(self, command: dict) -> bool:
        data = (json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8")
        with self._guard:
            sock = self._socket
        if sock is None:
            return False  # Never replay an action after a reconnect.
        try:
            self._outbox.put_nowait((sock, data))
            return True
        except queue.Full:
            self.status.emit("Milo is busy. Please try again in a moment.")
            return False

    def run(self):
        sender = threading.Thread(target=self._write, name="milo-desktop-send", daemon=True)
        sender.start()
        while not self._stop.is_set():
            sock = None
            try:
                sock = system.connect_local(self.path, 3.0)
                sock.settimeout(None)
                with self._guard:
                    self._socket = sock
                self.connection_changed.emit(True)
                with sock.makefile("rb") as stream:
                    while not self._stop.is_set():
                        raw = stream.readline(MAX_LINE + 1)
                        if not raw:
                            break
                        if len(raw) > MAX_LINE:
                            raise ValueError("The brain sent a message too large to display")
                        decoded = json.loads(raw)
                        if not isinstance(decoded, dict):
                            raise ValueError("The brain sent an invalid message")
                        self.event.emit(decoded)
            except (OSError, ValueError) as error:
                if not self._stop.is_set():
                    self.status.emit(str(error))
            finally:
                with self._guard:
                    self._socket = None
                if sock is not None:
                    sock.close()
                self.connection_changed.emit(False)
            self._stop.wait(0.75)
        self._outbox.put(None)
        sender.join(timeout=2)

    def _write(self):
        while (item := self._outbox.get()) is not None:
            sock, data = item
            with self._guard:
                current = self._socket
            if current is not sock:
                continue
            try:
                sock.sendall(data)
            except OSError:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def close(self):
        self._stop.set()
        with self._guard:
            sock = self._socket
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.wait(4500)
