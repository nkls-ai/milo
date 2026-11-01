"""Office actor protocol and GUI responsiveness, without opening user documents."""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtWidgets import QApplication

from milo.desktop.office_client import OfficeClient, is_office_request
from milo.desktop.office_worker import handle
from milo.entrypoints import module_command


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def until(app, condition, timeout=10):
    end = time.monotonic() + timeout
    while not condition() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)
    assert condition(), "Qt operation did not finish in time"


class Office:
    def __init__(self):
        self.described = False

    def describe(self, tool, args):
        self.described = True
        return {"app": args["app"], "document": "Budget", "filled": 1}

    def run(self, tool, args):
        assert self.described
        return {"text": "updated"}


def test_worker_preserves_strategy_state_and_rejects_nonoffice_code_entrypoints():
    office = Office()
    request = {"id": 1, "operation": "describe", "tool": "sheet_write",
               "args": {"app": "Microsoft Excel", "rows": [[1]]}}
    assert handle(request, office)["result"]["filled"] == 1
    assert handle({**request, "id": 2, "operation": "run"}, office)["result"] == {"text": "updated"}
    for tool in ("run_applescript", "run_script", "milo.server", "../../module.py"):
        assert not handle({**request, "tool": tool}, office)["ok"]
    assert not handle({**request, "module": "os"}, office)["ok"]
    assert not handle({**request, "args": {**request["args"], "output_path": "/arbitrary/path"}}, office)["ok"]


def test_real_worker_uses_only_json_stdout_and_creates_files_without_qt(tmp_path):
    pytest.importorskip("docx")
    request = {"id": 1, "operation": "describe", "tool": "write_document",
               "args": {"app": "TextEdit", "text": "Hello\nGrüße"}}
    data = "\n".join(json.dumps(item) for item in (request, {**request, "id": 2, "operation": "run"})) + "\n"
    result = subprocess.run(module_command("milo.desktop.office_worker", "--home", str(tmp_path)),
                            input=data, text=True, encoding="utf-8", capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == 2 and all(response["ok"] for response in responses)
    made = responses[1]["result"]
    assert not made["opened"] and Path(made["path"]).is_file()
    from docx import Document
    assert [p.text for p in Document(made["path"]).paragraphs] == ["Hello", "Grüße"]


class HangingProcess(QObject):
    started = Signal()
    readyReadStandardOutput = Signal()
    readyReadStandardError = Signal()
    errorOccurred = Signal(object)
    finished = Signal(int, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.running = False
        self.killed = False
        self.packets = []

    def setProgram(self, program):
        self.program = program

    def setArguments(self, args):
        self.args = args

    def setProcessEnvironment(self, environment):
        pass

    def start(self):
        self.running = True
        QTimer.singleShot(0, self.started.emit)

    def state(self):
        return QProcess.ProcessState.Running if self.running else QProcess.ProcessState.NotRunning

    def write(self, packet):
        self.packets.append(packet)
        return len(packet)

    def processId(self):
        return 0  # never signal a real process in this fake

    def kill(self):
        self.running, self.killed = False, True
        self.finished.emit(1, QProcess.ExitStatus.CrashExit)

    def readAllStandardOutput(self):
        return b""

    def readAllStandardError(self):
        return b""


EVENT = {"type": "hands_request", "id": "office-1", "tool": "write_document",
         "args": {"app": "TextEdit", "text": "Test"}}


def test_timeout_keeps_qt_responsive_kills_worker_and_never_replays(app, tmp_path):
    made, answers, ticks = [], [], []

    def factory(parent):
        process = HangingProcess(parent)
        made.append(process)
        return process

    client = OfficeClient(tmp_path, timeout_ms=40, process_factory=factory)
    ticker = QTimer()
    ticker.setInterval(5)
    ticker.timeout.connect(lambda: ticks.append(True))
    ticker.start()
    client.request(EVENT, answers.append)
    until(app, lambda: bool(answers))
    ticker.stop()
    assert len(ticks) >= 2 and made[0].killed
    assert len(answers) == 1 and not answers[0]["ok"] and "Inspect the document" in answers[0]["error"]
    assert len(made[0].packets) == 1
    assert "milo.desktop.office_worker" in made[0].args
    client.close()


def test_stop_completes_once_and_drops_a_busy_request_without_queueing(app, tmp_path):
    made, answers, busy = [], [], []

    def factory(parent):
        process = HangingProcess(parent)
        made.append(process)
        return process

    client = OfficeClient(tmp_path, process_factory=factory)
    client.request(EVENT, answers.append)
    client.request({**EVENT, "id": "office-2"}, busy.append)
    app.processEvents()
    client.cancel()
    app.processEvents()
    assert len(answers) == len(busy) == 1
    assert "already running" in busy[0]["error"] and "stopped" in answers[0]["error"]
    assert made[0].killed and len(made) == 1
    client.close()


def test_real_qprocess_completion_returns_to_gui_and_close_reaps_worker(app, tmp_path):
    pytest.importorskip("docx")
    answers, ticks = [], []
    client = OfficeClient(tmp_path)
    ticker = QTimer()
    ticker.setInterval(5)
    ticker.timeout.connect(lambda: ticks.append(True))
    ticker.start()
    started = time.monotonic()
    client.request(EVENT, answers.append)
    assert time.monotonic() - started < 0.5
    until(app, lambda: bool(answers), timeout=15)
    ticker.stop()
    assert ticks and answers[0]["ok"] and Path(answers[0]["result"]["path"]).is_file()
    worker = client._process
    client.close()
    until(app, lambda: worker.state() == QProcess.ProcessState.NotRunning)


def test_request_detection_accepts_only_structured_office_hands_events():
    assert is_office_request(EVENT)
    assert is_office_request({"type": "hands_request", "tool": "describe", "args": {"tool": "sheet_write"}})
    assert not is_office_request({"type": "hands_request", "tool": "describe", "args": {"tool": "click"}})
    assert not is_office_request({"type": "app_request", "tool": "write_document"})
