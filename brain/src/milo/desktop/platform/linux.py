"""Linux (X11): key injection through XTest and idle time through the screensaver extension.

X11 has no marker on synthetic events, so the hotkey listener ignores input while Milo injects
(`NativeBridge.input_busy`). Under Wayland the compositor owns global keys and synthetic input; the
listener reports that instead of pretending (`milo.desktop.hotkeys`).
"""
from __future__ import annotations

import os


class LinuxKeys:
    """The `KeyPlatform` for X11 (and what is possible of it under Wayland)."""

    polls = False

    def __init__(self):
        self._keys = None
        self._display = None

    def is_down(self, name: str) -> bool | None:
        return None  # the X11 listener sees every release; nothing to reconcile

    def other_down(self, name: str) -> bool:
        return False

    def listener_options(self) -> dict:
        return {}

    def paste_keys(self) -> None:
        from .ports import NativeError
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            raise NativeError("Wayland doesn't let apps type into other apps. Your words are ready to copy.")
        if self._keys is None:
            from pynput import keyboard
            self._keys = keyboard
            self._controller = keyboard.Controller()
        # XTest physical events: pynput's text path uses XSendEvent, which many XWayland clients ignore.
        v = self._keys.KeyCode.from_vk(ord("v"))
        self._controller.press(self._keys.Key.ctrl)
        try:
            self._controller.press(v)
            self._controller.release(v)
        finally:
            self._controller.release(self._keys.Key.ctrl)

    def type_text(self, text: str) -> bool:
        """Not on X11 yet: pynput's text typing uses XSendEvent, which many clients ignore. The paste is used."""
        return False

    def blocked(self, pid: int | None) -> str:
        return ""

    def mask_menu(self, name: str) -> None:
        pass  # X11 desktops don't open a menu on a lone Alt release

    def idle_s(self) -> float:
        try:
            if self._display is None:
                from Xlib import display
                from Xlib.ext import screensaver  # noqa: F401  registers screensaver_query_info
                self._display = display.Display()
            return self._display.screen().root.screensaver_query_info().idle / 1000.0
        except Exception:
            return 0.0


def accessibility():
    from .._native_linux import LinuxAccessibility
    return LinuxAccessibility()
