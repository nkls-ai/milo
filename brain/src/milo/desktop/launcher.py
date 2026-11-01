"""Own only the brain this desktop starts; leave an independently running brain alone."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal, Slot

from milo import system
from milo.entrypoints import runtime_executable


class BrainLauncher(QObject):
    status = Signal(str)
    setup_needed = Signal()

    def __init__(self, home: Path, parent=None):
        super().__init__(parent)
        self.home = home
        self.process: QProcess | None = None
        self._external = False
        self._stopping = False

    def ensure(self):
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        if self.process is not None:
            self.stop()
        lock = self.home / "run" / "brain.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if not system.try_lock(descriptor):
                self._external = True
                self.status.emit("Connecting to your running Milo brain…")
                return
        finally:
            os.close(descriptor)
        self._external = False
        process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("MILO_HOME", str(self.home))
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)
        logs = self.home / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        process.setStandardOutputFile(str(logs / "brain.stdout.log"), QProcess.OpenModeFlag.Append)
        process.setStandardErrorFile(str(logs / "brain.stdout.log"), QProcess.OpenModeFlag.Append)
        process.errorOccurred.connect(self._failed)
        process.finished.connect(self._finished)
        process.setProgram(runtime_executable())
        process.setArguments(["--brain"] if getattr(sys, "frozen", False) else ["-m", "milo.server"])
        self.process = process
        process.start()
        self.status.emit("Starting Milo's brain…")

    @Slot(QProcess.ProcessError)
    def _failed(self, _):
        if self.sender() is self.process and not self._stopping:
            self.status.emit("The brain couldn't start. Check logs/brain.stdout.log, then use Restart brain.")

    @Slot(int, QProcess.ExitStatus)
    def _finished(self, code, _):
        if self.sender() is self.process and not self._stopping:
            self.status.emit(f"The brain stopped (exit {code}). Check logs/brain.stdout.log, then use Restart brain.")

    def apply_configuration(self):
        if self._external:
            self.status.emit("Saved. Restart the brain in the terminal where you started it.")
        elif self.process is None:
            self.ensure()
        else:
            self.restart()

    def restart(self):
        if self.process is None:
            self.status.emit("This brain was started elsewhere. Restart it in that terminal.")
            return
        self.status.emit("Saved. Restarting Milo's brain…")
        self.stop()
        self.ensure()

    def stop(self):
        self._stopping = True
        process, self.process = self.process, None
        if process is not None:
            process.errorOccurred.disconnect(self._failed)
            process.finished.disconnect(self._finished)
            if process.state() != QProcess.ProcessState.NotRunning:
                system.signal_processes(int(process.processId()), [], force=False)
                if not process.waitForFinished(2500):
                    process.kill()
                    process.waitForFinished(1000)
            process.setParent(None)
            process.deleteLater()
        self._stopping = False
