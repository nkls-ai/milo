"""Real process recovery: saving valid settings restarts once, without reopening setup."""
import os
import time
import gc
import weakref

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QProcess
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from milo import system
from milo.desktop.launcher import BrainLauncher

CONFIG = '''
[chat]
use = "none"
[harness]
use = "none"
[stt]
use = "none"
[tts]
use = "none"
fallback = ""
[audio]
use = "none"
[connections]
use = "none"
[dictation]
use = "plain"
[heartbeat]
enabled = false
[memory]
enabled = false
[hands]
enabled = false
[weather]
enabled = false
[decide]
use = "none"
'''


def until(app, condition):
    deadline = time.monotonic() + 20
    while not condition():
        assert time.monotonic() < deadline, "Brain process did not reach the expected state"
        app.processEvents()
        time.sleep(.01)
    app.processEvents()


def test_save_after_failure_and_repeated_restart_do_not_reopen_setup(tmp_path):
    app = QApplication.instance() or QApplication([])
    home = tmp_path / "Milo"
    home.mkdir()
    config = home / "config.toml"
    config.write_text('[broken', encoding="utf-8")
    launcher = BrainLauncher(home)
    setup_windows, status = [], []
    launcher.setup_needed.connect(lambda: setup_windows.append(True))
    launcher.status.connect(status.append)
    try:
        launcher.ensure()
        until(app, lambda: launcher.process.state() == QProcess.ProcessState.NotRunning)
        assert not setup_windows, "A startup failure must not reopen the provider dialog"
        config.write_text(CONFIG, encoding="utf-8")

        def connected():
            try:
                system.connect_local(home / "run" / "brain.sock", .2).close()
                return True
            except OSError:
                return False

        launcher.apply_configuration()
        until(app, connected)
        first_pid = int(launcher.process.processId())
        launcher.apply_configuration()
        until(app, connected)
        assert int(launcher.process.processId()) != first_pid
        assert not setup_windows
        assert any("Restarting" in text for text in status)
    finally:
        launcher.stop()
    # Collecting a launcher with stopped children must not leave signal cycles
    # or deferred Qt callbacks that crash the next UI event loop.
    released = weakref.ref(launcher)
    del launcher
    gc.collect()
    QTest.qWait(80)
    assert released() is None
