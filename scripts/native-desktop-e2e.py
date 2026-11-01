"""Exercise actual desktop adapters against a disposable Qt application owned by this test.

Run from a graphical session with `uv run --project brain --extra desktop python
scripts/native-desktop-e2e.py`. No personal app is edited. The report records the
OS/session and focus timing; a missing accessibility service is a failure, not a pass.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def fixture(directory: Path) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QVBoxLayout, QWidget

    app = QApplication([])
    window = QWidget()
    window.setWindowTitle("Milo disposable native integration test")
    window.resize(560, 170)
    layout = QVBoxLayout(window)
    layout.addWidget(QLabel("Milo's automated test owns this field. It closes when the test finishes."))
    field = QLineEdit("before")
    field.setAccessibleName("Milo test field")
    layout.addWidget(field)
    last_control = [0]

    def save():
        data = json.dumps({"pid": os.getpid(), "text": field.text(), "control": last_control[0]})
        try:
            (directory / "fixture.json").write_text(data, encoding="utf-8")
        except PermissionError:
            QTimer.singleShot(30, save)

    field.textChanged.connect(save)
    window.show()
    def activate():
        window.raise_()
        window.activateWindow()
        field.setFocus()
        field.setCursorPosition(len(field.text()))
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(window.winId()))
        save()
    QTimer.singleShot(300, activate)
    def control():
        try:
            command = json.loads((directory / "control.json").read_text(encoding="utf-8"))
            if command["id"] == last_control[0]:
                return
            if "cursor" in command:
                field.setCursorPosition(int(command["cursor"]))
            if "selection" in command:
                field.setSelection(*command["selection"])
            last_control[0] = command["id"]
            save()
        except (OSError, ValueError, KeyError):
            pass
    control_timer = QTimer(window)
    control_timer.setInterval(40)
    control_timer.timeout.connect(control)
    control_timer.start()
    QTimer.singleShot(60000, app.quit)
    return app.exec()


def run(output: Path) -> int:
    from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
    from milo.desktop.native import NativeBridge, writable
    from milo.desktop._native_types import UnavailableAccessibility

    app = QApplication([])
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="milo-native-", dir=output) as temporary:
        directory = Path(temporary)
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--fixture", str(directory)],
                                 env={**os.environ, "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1"})
        bridge = NativeBridge(directory)
        fixture_pid = child.pid
        if isinstance(bridge.backend, UnavailableAccessibility):
            child.terminate()
            raise RuntimeError(bridge.backend.reason)
        clipboard = bridge.clipboard.snapshot()

        def wait_for(predicate, message, timeout=15):
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                app.processEvents()
                if child.poll() is not None:
                    raise RuntimeError(f"Fixture exited with {child.returncode}")
                try:
                    value = predicate()
                    if value:
                        return value
                except (OSError, ValueError):
                    pass
                time.sleep(0.03)
            focus = bridge.backend.focus()
            diagnostics = {"pid": focus.pid, "role": focus.role, "editable": focus.editable,
                           "secure": focus.secure} if focus else None
            if focus is not None and focus.pid == fixture_pid:
                diagnostics["owned_field_text"] = focus.text
            try:
                fixture_text = contents()
            except (OSError, ValueError):
                fixture_text = "<unreadable>"
            owned = [{"role": value.role, "editable": value.editable, "title": value.title}
                     for window in bridge.backend.windows() if window.pid == fixture_pid
                     for value in bridge.backend.elements(window.app)]
            xfocus = None
            if getattr(bridge.backend, "display", None):
                window = bridge.backend.display.get_input_focus().focus
                xfocus = getattr(window, "id", window)
            raise AssertionError(f"{message}; focus={diagnostics}; owned_fixture_text={fixture_text!r}; "
                                 f"fixture_controls={owned}; x_input_focus={xfocus}")

        def contents():
            return json.loads((directory / "fixture.json").read_text(encoding="utf-8"))["text"]

        control_id = [0]
        def control(**values):
            control_id[0] += 1
            (directory / "control.json").write_text(json.dumps({"id": control_id[0], **values}), encoding="utf-8")
            wait_for(lambda: json.loads((directory / "fixture.json").read_text(encoding="utf-8"))["control"] == control_id[0],
                     "The owned field did not receive its cursor/selection control")

        try:
            wait_for(lambda: (directory / "fixture.json").exists(), "Fixture never became ready")
            fixture_pid = json.loads((directory / "fixture.json").read_text(encoding="utf-8"))["pid"]
            bridge.backend.activate("Milo disposable native integration test")
            target = wait_for(lambda: (t if t and t.pid == fixture_pid and writable(t) and bridge._keyboard_target(t) else None)
                              if (t := bridge.backend.focus()) else None, "Fixture field did not gain accessible focus")
            started = time.perf_counter()
            for _ in range(10):
                bridge.backend.focus()
            focus_ms = (time.perf_counter() - started) * 100
            bridge.remember_focus()
            phrase = " Grüß dich, Milo 🐦"
            pasted = bridge.paste_dictation(phrase)
            assert pasted.get("pasted"), pasted
            wait_for(lambda: contents() == "before" + phrase, "Clipboard paste did not reach the test field")
            undo = bridge.app_request("text.unwrite", {"field": pasted["field"], "text": phrase})
            assert undo.get("removed"), undo
            wait_for(lambda: contents() == "before", "Undo did not restore the test field")
            tree = bridge.hands_request("ax_tree", {})
            element = next(identifier for identifier, value in bridge._elements.items()
                           if value.pid == fixture_pid and value.editable and value.title == "Milo test field")
            bridge.hands_request("ax_set_value", {"element": element, "text": "UIA or AT-SPI set this exact field"})
            wait_for(lambda: contents() == "UIA or AT-SPI set this exact field", "Accessibility write failed")
            capture = bridge.capture("window")
            assert capture.get("image") and not capture.get("error"), capture
            bridge.backend.set_value(bridge.backend.focus(), "left right")
            wait_for(lambda: contents() == "left right", "Middle-field fixture could not be reset")
            control(cursor=5)
            bridge.remember_focus()
            middle = bridge.paste_dictation("middle ")
            assert middle.get("pasted"), middle
            wait_for(lambda: contents() == "left middle right", "Middle-field paste did not land at its caret")
            assert bridge.app_request("text.unwrite", {"field": middle["field"], "text": "middle "}).get("removed"), "Middle-field undo failed"
            wait_for(lambda: contents() == "left right", "Middle-field undo did not restore surrounding text")
            bridge.backend.set_value(bridge.backend.focus(), "left old right")
            wait_for(lambda: contents() == "left old right", "Selection fixture could not be reset")
            control(selection=[5, 3])
            bridge.remember_focus()
            selected = bridge.paste_dictation("new")
            assert selected.get("pasted"), selected
            wait_for(lambda: contents() == "left new right", "Paste did not replace the owned selection")
            assert bridge.app_request("text.unwrite", {"field": selected["field"], "text": "new"}).get("removed"), "Selection replacement undo failed"
            wait_for(lambda: contents() == "left old right", "Undo did not restore the replaced selection")
            # Model an explicit click on Milo's on-screen Finish control. Only
            # the exact remembered external field may regain focus and input.
            control(cursor=8)
            bridge.remember_focus()
            finish_window = QWidget()
            finish_window.setWindowTitle("Milo disposable Finish control")
            finish_layout = QVBoxLayout(finish_window)
            finish_field = QLineEdit("Test-owned Milo control")
            finish_layout.addWidget(finish_field)
            finish_window.show()
            finish_window.raise_()
            finish_window.activateWindow()
            finish_field.setFocus()
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(int(finish_window.winId()))
            wait_for(lambda: bridge.backend.foreground_pid() == os.getpid(),
                     "Owned Finish control did not gain focus")
            bridge.arm_return_to_dictation_target()
            returned = bridge.paste_dictation(" return")
            assert returned.get("pasted"), f"Explicit Finish did not return to captured field: {returned}"
            wait_for(lambda: contents() == "left old return right", "Finish returned to the wrong caret or field")
            assert bridge.app_request("text.unwrite", {"field": returned["field"], "text": " return"}).get("removed")
            wait_for(lambda: contents() == "left old right", "Finish-return undo did not restore the field")
            finish_window.close()
            # Observe a real accessible field while using a deterministic clock
            # for the 45-second expiry, keeping this E2E fast and reproducible.
            from milo.desktop.corrections import CorrectionObserver
            now = [0.0]
            bridge._corrections = CorrectionObserver(writable, clock=lambda: now[0])
            bridge.backend.set_value(bridge.backend.focus(), "")
            wait_for(lambda: contents() == "", "Correction fixture could not be reset")
            bridge.remember_focus()
            dictated = "I use Cloud Code every day."
            assert bridge.paste_dictation(dictated).get("pasted")
            wait_for(lambda: contents() == dictated, "Correction fixture paste failed")
            now[0] = 0.4
            bridge.poll_focus()
            bridge.backend.set_value(bridge.backend.focus(), "I use Claude Code every day.")
            wait_for(lambda: contents() == "I use Claude Code every day.", "Owned correction edit failed")
            bridge.poll_focus()
            now[0] = 46.0
            bridge.poll_focus()
            assert bridge.take_corrections() == [("Cloud Code", "Claude Code")], "Correction observer did not learn the owned-field edit"
            screenshot = output / "native-e2e.png"
            screenshot.write_bytes(Path(capture["image"]).read_bytes())
            report = {"platform": sys.platform, "session": os.environ.get("XDG_SESSION_TYPE", "x11" if sys.platform.startswith("linux") else "windows"),
                      "backend": type(bridge.backend).__name__, "focus_ms_mean": round(focus_ms, 2),
                      "checks": ["owned-window focus", "unicode clipboard paste", "exact-field undo",
                                 "accessibility tree", "accessibility set value", "screen capture", "correction field observer",
                                 "middle-field undo", "selection replacement undo", "explicit Finish returns to captured field"],
                      "field_role": target.role, "tree": tree["text"][:1500],
                      "screenshot": str(screenshot.resolve())}
            (output / "native-e2e.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False))
            return 0
        finally:
            bridge.clipboard.clipboard.setMimeData(clipboard)
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/native-e2e"))
    args = parser.parse_args()
    raise SystemExit(fixture(args.fixture) if args.fixture else run(args.output))
