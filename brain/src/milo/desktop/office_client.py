"""A bounded asynchronous Office actor client. COM never runs on the GUI thread."""
from __future__ import annotations

import itertools
import json
import os
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer

from milo import system
from milo.entrypoints import module_command

from .office_worker import MAX_LINE, TOOLS

TIMEOUT_MS = 15_000
UNCERTAIN = "Office may have applied part of the operation. Inspect the document before trying again."


def is_office_request(event: dict) -> bool:
    if event.get("type") != "hands_request":
        return False
    tool, args = event.get("tool"), event.get("args") or {}
    return isinstance(tool, str) and (tool in TOOLS or (tool == "describe" and isinstance(args, dict)
                                                        and isinstance(args.get("tool"), str) and args["tool"] in TOOLS))


class OfficeClient(QObject):
    """One in-flight request, one persistent worker, no replay after cancellation."""

    def __init__(self, home: Path, parent=None, *, timeout_ms: int = TIMEOUT_MS,
                 process_factory: Callable = QProcess):
        super().__init__(parent)
        self.home = home
        self._factory = process_factory
        self._process: QProcess | None = None
        self._pending: tuple[int, dict, Callable] | None = None
        self._packet: bytes | None = None
        self._buffer = bytearray()
        self._ids = itertools.count(1)
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(10, timeout_ms))
        self._timer.timeout.connect(lambda: self._abort("Office took too long to answer. " + UNCERTAIN))

    def request(self, event: dict, on_complete: Callable[[dict], None]) -> None:
        """Return immediately; completion is delivered on this object's Qt thread."""
        if self._closed or self._pending is not None or not is_office_request(event):
            error = "The Office connection is closed." if self._closed else (
                "An Office operation is already running. Wait or press Stop." if self._pending else "Unsupported Office request.")
            QTimer.singleShot(0, lambda: on_complete(self._answer(event, error=error)))
            return
        identity = next(self._ids)
        if not isinstance(event.get("args") or {}, dict):
            QTimer.singleShot(0, lambda: on_complete(self._answer(event, error="Office arguments must be an object.")))
            return
        args = dict(event.get("args") or {})
        tool = str(event["tool"])
        operation = "describe" if tool == "describe" else "run"
        if operation == "describe":
            tool = str(args.pop("tool"))
        try:
            packet = (json.dumps({"id": identity, "operation": operation, "tool": tool, "args": args},
                                 ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            QTimer.singleShot(0, lambda: on_complete(self._answer(event, error="Invalid Office request data.")))
            return
        if len(packet) > MAX_LINE:
            QTimer.singleShot(0, lambda: on_complete(self._answer(event, error="Office request too large.")))
            return
        self._pending = (identity, dict(event), on_complete)
        self._packet = packet
        self._timer.start()
        if self._process is None:
            self._start()
        elif self._process.state() == QProcess.ProcessState.Running:
            self._write()
        elif self._process.state() == QProcess.ProcessState.NotRunning:
            self._process = None
            self._start()

    def _start(self) -> None:
        process = self._factory(self)
        self._process = process
        self._buffer.clear()
        command = module_command("milo.desktop.office_worker", "--home", str(self.home))
        process.setProgram(command[0])
        process.setArguments(list(command[1:]))
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("MILO_OFFICE_PARENT_PID", str(os.getpid()))
        process.setProcessEnvironment(environment)
        process.started.connect(lambda: self._write() if self._process is process else None)
        process.readyReadStandardOutput.connect(lambda: self._read(process))
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.errorOccurred.connect(lambda _error: self._abort("The Office worker couldn't run. " + UNCERTAIN)
                                       if self._process is process else None)
        process.finished.connect(lambda *_: self._finished(process))
        process.start()

    def _write(self) -> None:
        if self._process is not None and self._packet is not None:
            packet, self._packet = self._packet, None
            if self._process.write(packet) < 0:
                self._abort("The Office worker disconnected. " + UNCERTAIN)

    def _read(self, process) -> None:
        if process is not self._process:
            process.readAllStandardOutput()
            return
        self._buffer.extend(bytes(process.readAllStandardOutput()))
        if len(self._buffer) > MAX_LINE:
            self._abort("The Office response was too large. " + UNCERTAIN)
            return
        while b"\n" in self._buffer:
            raw, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            try:
                response = json.loads(raw)
                if (not isinstance(response, dict) or self._pending is None
                        or type(response.get("id")) is not int or response["id"] != self._pending[0]):
                    raise ValueError
                if not isinstance(response.get("ok"), bool) or (response["ok"] and not isinstance(response.get("result"), dict)):
                    raise ValueError
            except (ValueError, RecursionError):
                self._abort("The Office worker sent an invalid response. " + UNCERTAIN)
                return
            _, event, callback = self._pending
            self._pending = None
            self._timer.stop()
            callback(self._answer(event, result=response.get("result") if response["ok"] else None,
                                  error=str(response.get("error") or "Office couldn't complete the operation.")
                                  if not response["ok"] else ""))

    def _finished(self, process) -> None:
        if self._process is process:
            self._read(process)
            if self._process is process:
                self._process = None
                if self._pending is not None:
                    self._complete_error("The Office worker stopped. " + UNCERTAIN)
        process.deleteLater()

    @staticmethod
    def _answer(event: dict, *, result: dict | None = None, error: str = "") -> dict:
        return {"type": "hands_result", "id": event.get("id", ""), "ok": not bool(error),
                "result": result or {}, "error": error}

    def _complete_error(self, error: str) -> None:
        self._timer.stop()
        self._packet = None
        self._buffer.clear()
        pending, self._pending = self._pending, None
        if pending is not None:
            _, event, callback = pending
            callback(self._answer(event, error=error))

    def _abort(self, error: str) -> None:
        process, self._process = self._process, None
        # Clear state before completion: callback may start the next request.
        pending, self._pending = self._pending, None
        self._timer.stop()
        self._packet = None
        self._buffer.clear()
        if process is not None:
            pid = int(process.processId())
            if pid:
                try:
                    system.signal_processes(pid, [], force=True)
                except OSError:
                    pass
            process.kill()
            if process.state() == QProcess.ProcessState.NotRunning:
                process.deleteLater()
        if pending is not None:
            _, event, callback = pending
            callback(self._answer(event, error=error))

    def cancel(self) -> None:
        self._abort("The Office operation was stopped. " + UNCERTAIN)

    def close(self) -> None:
        self._closed = True
        self.cancel()
