"""Opt-in real OS hooks. Close other Milo instances before injecting modifiers.

MILO_REAL_HOTKEYS=1 uv run pytest tests/desktop/test_native_hotkeys_e2e.py
Only a test-owned Qt window receives modifiers; no microphone, brain, text,
clipboard or desktop action is connected to the production hotkey controller.
"""
import os
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("MILO_REAL_HOTKEYS") != "1",
                               reason="opt-in actual desktop modifier injection")


def test_real_hold_modifiers_reach_production_listener():
    from PySide6.QtWidgets import QApplication, QWidget
    from milo.desktop.hotkeys import GlobalHotkeys

    app = QApplication.instance() or QApplication([])
    window = QWidget()
    window.setWindowTitle("Milo disposable hotkey integration test")
    window.resize(320, 120)
    window.show()
    window.activateWindow()
    events, statuses = [], []
    hotkeys = GlobalHotkeys(on_command=events.append)
    hotkeys.status.connect(statuses.append)

    def wait_for(predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate():
            app.processEvents()
            assert time.monotonic() < deadline, (events, statuses)
            time.sleep(.005)

    if sys.platform == "win32":
        import ctypes

        def key(mode, pressed):
            vk, scan = (0xA3, 0x1D) if mode == "dictate" else (0xA5, 0x38)
            ctypes.windll.user32.keybd_event(vk, scan, 1 | (0 if pressed else 2), 0)
    else:
        from Xlib import X, XK, display
        from Xlib.ext import xtest
        connection = display.Display()

        def key(mode, pressed):
            symbols = ["Control_R"] if mode == "dictate" else ["Alt_R", "ISO_Level3_Shift", "Mode_switch"]
            codes = [connection.keysym_to_keycode(XK.string_to_keysym(symbol)) for symbol in symbols]
            code = next((code for code in codes if code), 0)
            assert code, f"No physical keycode for {symbols}"
            xtest.fake_input(connection, X.KeyPress if pressed else X.KeyRelease, code)
            connection.sync()

    held = None
    try:
        hotkeys.start()
        wait_for(lambda: hotkeys._keyboard is not None and hotkeys._keyboard.running)
        # Listener.running precedes hook installation. Observe its ready flag
        # with a bound rather than calling the library's unbounded wait().
        wait_for(lambda: hotkeys._keyboard._ready)
        if sys.platform == "win32":
            from pynput._util.win32 import SystemHook
            wait_for(lambda: bool(getattr(SystemHook._HOOKS.get(hotkeys._keyboard.ident), "_hook", None)))
        for mode in ("dictate", "talk"):
            events.clear()
            key(mode, True)
            held = mode
            wait_for(lambda: any(e["type"] == "listen_confirm" for e in events))
            held_until = time.monotonic() + 0.3  # a real hold: shorter is a tap
            wait_for(lambda: time.monotonic() >= held_until)
            key(mode, False)
            held = None
            wait_for(lambda: any(e["type"] == "listen_stop" for e in events))
            assert events == [{"type": "listen_start", "mode": mode, "tentative": True},
                              {"type": "listen_confirm"}, {"type": "listen_stop"}]
        assert not statuses
    finally:
        if held is not None:
            key(held, False)
        hotkeys.stop()
        window.close()
        if sys.platform != "win32":
            connection.close()
