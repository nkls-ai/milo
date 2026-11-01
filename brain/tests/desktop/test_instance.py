"""Actual local sockets and process-held desktop ownership, without the brain."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalSocket

from milo.desktop.instance import DesktopInstance, server_name
from milo import system
from milo.transport.instance_lock import AlreadyRunning, acquire


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, predicate, seconds=8):
    deadline = time.monotonic() + seconds
    while not predicate():
        app.processEvents()
        assert time.monotonic() < deadline, "desktop activation timed out"
        time.sleep(.005)


CLIENT = """
import json, sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from milo.desktop.instance import DesktopInstance
app = QCoreApplication([])
instance = DesktopInstance(Path(sys.argv[1]))
owner = instance.start()
print(json.dumps([owner, instance.activation_delivered]), flush=True)
instance.close()
"""

OWNER = """
import os, sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from milo.desktop.instance import DesktopInstance
app = QCoreApplication([])
instance = DesktopInstance(Path(sys.argv[1]))
assert instance.start()
print(os.getpid(), flush=True)
app.exec()
"""


def test_second_process_activates_owner_without_taking_its_lock(app, tmp_path):
    owner = DesktopInstance(tmp_path)
    activated = []
    owner.activation_requested.connect(lambda: activated.append(True))
    assert owner.start()
    assert owner._fd is not None and not os.get_inheritable(owner._fd)
    client = subprocess.Popen([sys.executable, "-c", CLIENT, str(tmp_path)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(app, lambda: client.poll() is not None)
        stdout, stderr = client.communicate(timeout=2)
        assert client.returncode == 0, stderr
        assert json.loads(stdout) == [False, True]
        assert activated == [True]
        with pytest.raises(AlreadyRunning):
            acquire(tmp_path / "run" / "desktop.lock")
    finally:
        if client.poll() is None:
            client.kill()
            client.wait(timeout=5)
        owner.close()
    replacement = DesktopInstance(tmp_path)
    try:
        assert replacement.start()
    finally:
        replacement.close()


def test_crashed_process_releases_kernel_lock_and_stale_endpoint_is_reclaimed(app, tmp_path):
    child = subprocess.Popen([sys.executable, "-c", OWNER, str(tmp_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    actual_pid = child.pid
    try:
        # Readiness comes before entering the event loop and requires no test sleep.
        actual_pid = int(child.stdout.readline().strip())
        with pytest.raises(AlreadyRunning):
            acquire(tmp_path / "run" / "desktop.lock")
    finally:
        system.signal_processes(child.pid, [actual_pid], force=True)
        child.wait(timeout=5)
    successor = DesktopInstance(tmp_path)
    try:
        assert successor.start()
    finally:
        successor.close()


def test_second_launch_retries_while_owner_is_still_starting(app, tmp_path):
    delayed_owner = OWNER.replace("from PySide6.QtCore import QCoreApplication",
                                 "from PySide6.QtCore import QCoreApplication, QTimer")
    delayed_owner = delayed_owner.replace("assert instance.start()", """
from milo.transport.instance_lock import acquire
instance._fd = acquire(instance.home / 'run' / 'desktop.lock')
QTimer.singleShot(200, lambda: instance._server.listen(instance.name))
""")
    child = subprocess.Popen([sys.executable, "-c", delayed_owner, str(tmp_path)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    actual_pid = child.pid
    contender = DesktopInstance(tmp_path)
    try:
        actual_pid = int(child.stdout.readline().strip())
        assert not contender.start()
        assert contender.activation_delivered
    finally:
        contender.close()
        system.signal_processes(child.pid, [actual_pid], force=True)
        child.wait(timeout=5)


def test_different_homes_can_own_desktops_and_close_is_idempotent(app, tmp_path):
    first, second = DesktopInstance(tmp_path / "a"), DesktopInstance(tmp_path / "b")
    try:
        assert first.name != second.name
        assert first.start() and first.start() and second.start()
    finally:
        first.close()
        first.close()
        second.close()


def test_activation_protocol_accepts_only_fixed_show_message(app, tmp_path):
    owner = DesktopInstance(tmp_path)
    activated = []
    owner.activation_requested.connect(lambda: activated.append(True))
    assert owner.start()
    socket = QLocalSocket()
    try:
        socket.connectToServer(owner.name)
        assert socket.waitForConnected(500)
        socket.write(b"run anything\n")
        socket.flush()
        wait_for(app, lambda: socket.state() == QLocalSocket.LocalSocketState.UnconnectedState)
        assert activated == []
    finally:
        socket.abort()
        owner.close()


def test_startup_race_retry_is_bounded_and_does_not_remove_owner_endpoint(app, tmp_path):
    fd = acquire(tmp_path / "run" / "desktop.lock")
    contender = DesktopInstance(tmp_path, activation_timeout_s=.1)
    started = time.monotonic()
    try:
        assert contender.start() is False
        assert not contender.activation_delivered
        assert time.monotonic() - started < 1
    finally:
        contender.close()
        os.close(fd)


def test_equivalent_home_paths_share_identity(tmp_path):
    assert server_name(tmp_path) == server_name(tmp_path / "a" / "..")
    if sys.platform == "win32":
        assert server_name(tmp_path) == server_name(Path(str(tmp_path).swapcase()))


def test_listen_failure_releases_kernel_ownership(app, tmp_path, monkeypatch):
    instance = DesktopInstance(tmp_path)
    monkeypatch.setattr(instance._server, "listen", lambda name: False)
    with pytest.raises(RuntimeError, match="local desktop activation"):
        instance.start()
    assert instance._fd is None
    fd = acquire(tmp_path / "run" / "desktop.lock")
    os.close(fd)
