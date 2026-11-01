"""Shared native bridge. All entry points run on the Qt GUI thread.

Accessibility, clipboard and input are separate interfaces so focus safety and
undo rules can be tested without sending input to the user's applications.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

from ._native_types import Accessibility, BorrowRequired, Focus, NativeError, UnavailableAccessibility

__all__ = ["NativeBridge", "NativeError", "BorrowRequired", "Focus"]

log = logging.getLogger("milo.desktop.native")

_TERMINAL = re.compile(r"terminal|powershell|pwsh|cmd(?:\.exe)?$|conhost|windowsterminal|alacritty|kitty|"
                       r"wezterm|konsole|xterm|gnome-terminal|bash|zsh|fish|wsl|code - insiders|visual studio code",
                       re.IGNORECASE)
_SECRET_APP = re.compile(r"1password|bitwarden|keepass|lastpass|dashlane|passwords|credential", re.IGNORECASE)


def writable(target: Focus | None) -> bool:
    """A field Milo may write into for a helper (text.write) and can undo: strictly verified (ADR 33)."""
    return bool(target and target.editable and not target.secure and target.pid != os.getpid() and
                not _TERMINAL.search(target.app) and not _SECRET_APP.search(target.app))


def _secret(target: Focus | None) -> bool:
    return bool(target and (target.secure or _SECRET_APP.search(target.app)))


_OPENING = frozenset("([{“‘„‚«/")


def spaced(text: str, before: str) -> str:
    """The Mac's DictationSpacing: a dictation goes on from the character before the caret. Right after a word
    or a full stop it needs a space; after a space, an opening bracket or quote, or at the start, it doesn't,
    and neither does text that starts with its own space or punctuation."""
    if not before or not text or before.isspace() or before in _OPENING or text[0].isspace():
        return text
    if unicodedata.category(text[0]).startswith("P"):
        return text
    return " " + text


@dataclass(frozen=True)
class _Write:
    target: Focus
    before_hash: bytes
    after_hash: bytes
    inserted: str
    offset: int
    replaced: str


# Windows: keep Milo's paste out of clipboard history (Win+V), cloud sync and clipboard managers.
_PRIVATE_FORMATS = ('application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"',
                    'application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"',
                    'application/x-qt-windows-mime;value="CanUploadToCloudClipboard"')


class QtClipboard:
    """The paste's clipboard: the user's own content comes back afterwards, unless they copied something new.

    Several pastes in a row (stream = "type") share one snapshot, so the user's content is what returns, not
    an earlier phrase. The restore waits `restore_s`: apps read the clipboard when they handle Ctrl+V, a busy
    browser or Electron app a few hundred milliseconds later.
    """
    restore_s = 0.8

    def __init__(self):
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance() is None:
            raise NativeError("The desktop application must be running before using its clipboard.")
        self.clipboard = QGuiApplication.clipboard()
        self._pending = None  # (snapshot, inserted, timer)

    def text(self) -> str:
        return self.clipboard.text()

    def set_text(self, text: str) -> None:
        from PySide6.QtCore import QMimeData
        data = QMimeData()
        data.setText(text)
        if sys.platform == "win32":
            for mime in _PRIVATE_FORMATS:
                data.setData(mime, b"\0\0\0\0")
        self.clipboard.setMimeData(data)

    def snapshot(self):
        pending = self._pending
        if pending is not None and self.clipboard.text() == pending[1]:
            pending[2].stop()
            self._pending = None
            return pending[0]  # still the user's content from before the previous paste
        from PySide6.QtCore import QMimeData
        old, copy = self.clipboard.mimeData(), QMimeData()
        if old:
            for mime in old.formats():
                if mime not in _PRIVATE_FORMATS:
                    copy.setData(mime, old.data(mime))
        return copy

    def restore_later(self, snapshot, inserted: str) -> None:
        from PySide6.QtCore import QTimer
        if self._pending is not None:
            self._pending[2].stop()
        timer = QTimer()
        timer.setSingleShot(True)

        def restore():
            self._pending = None
            if self.clipboard.text() == inserted:
                self.clipboard.setMimeData(snapshot)

        timer.timeout.connect(restore)
        timer.start(round(self.restore_s * 1000))
        self._pending = (snapshot, inserted, timer)

    def keep(self, inserted: str) -> None:
        """Leave `inserted` on the clipboard: the user pastes it themselves."""
        if self._pending is not None and self._pending[1] == inserted:
            self._pending[2].stop()
            self._pending = None


class PynputInput:
    def __init__(self):
        from pynput import keyboard, mouse
        self.keyboard, self.mouse = keyboard, mouse
        self.keys, self.pointer = keyboard.Controller(), mouse.Controller()
        from milo.adapters.platform import current
        from milo.adapters.risk_policy import for_platform
        self.policy = for_platform(current().name)

    def shortcut(self, combo: str) -> None:
        parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
        policy_aliases = dict(self.policy.key_aliases)
        aliases = {"command": "cmd",
                   "option": "alt", "control": "ctrl", "return": "enter", "escape": "esc",
                   "forwarddelete": "delete", "delete": "delete", "backspace": "backspace",
                   "keypadenter": "enter", "pageup": "page_up", "pagedown": "page_down"}
        if not parts or len(parts) > 5:
            raise NativeError("Use a key or shortcut such as ctrl+s.")
        keys = []
        for part in parts:
            part = policy_aliases.get(part, part)
            part = aliases.get(part, part)
            key = getattr(self.keyboard.Key, part, None)
            if key is None and len(part) != 1:
                raise NativeError(f"Unknown key: {part}")
            if key is None and sys.platform.startswith("linux") and part.isascii() and part.isalnum():
                # Shortcut letters use XTest physical events. Pynput's general
                # text path uses XSendEvent, which some XWayland clients ignore.
                key = self.keyboard.KeyCode.from_vk(ord(part))
            keys.append(key or part)
        pressed = []
        try:
            for key in keys:
                self.keys.press(key)
                pressed.append(key)
        finally:
            for key in reversed(pressed):
                self.keys.release(key)

    def click(self, x: int, y: int, button: str, double: bool) -> None:
        self.pointer.position = (x, y)
        self.pointer.click(getattr(self.mouse.Button, button), 2 if double else 1)

    def scroll(self, dx: int, dy: int, point: tuple[int, int] | None) -> None:
        if point:
            self.pointer.position = point
        self.pointer.scroll(dx, -dy)


def default_accessibility() -> Accessibility:
    try:
        if sys.platform == "win32":
            from .platform.windows import accessibility
            return accessibility()
        if sys.platform.startswith("linux"):
            from .platform.linux import accessibility
            return accessibility()
        return UnavailableAccessibility("Use Milo's native macOS app for accessibility on this platform.")
    except Exception as e:
        return UnavailableAccessibility(f"Desktop accessibility is unavailable: {e}")


class NativeBridge:
    """The `DesktopPlatform` (see `platform/ports.py`): focus, paste, undo, corrections, capture, hands, meetings.

    `backend` is the OS accessibility tree, `keys` the OS key platform (paste keys, idle time), `input_device`
    the worker's synthetic keyboard and mouse.
    """

    def __init__(self, home: Path, *, backend: Accessibility | None = None, clipboard=None, input_device=None,
                 keys=None):
        self.home = Path(home)
        self.backend = backend if backend is not None else default_accessibility()
        if keys is None:
            from .platform import keys as platform_keys
            keys = platform_keys()
        self.keys = keys
        self._clipboard = clipboard
        self._input = input_device
        self._remembered: Focus | None = None
        self._external: Focus | None = None
        self._dictation_return: tuple[str, int, float] | None = None
        self._elements: dict[str, Focus] = {}
        self._writes: dict[str, _Write] = {}
        self._borrowed: dict[str, float] = {}
        self._synthetic_until = 0.0
        self._shot: tuple[int, int, int, int, float] | None = None
        self._checked: Focus | None = None
        self._meeting_recorder = None
        self._office_tools = None
        from .corrections import CorrectionObserver
        from ._native_words import SystemWords
        self._corrections = CorrectionObserver(writable, words=SystemWords())

    @property
    def input_busy(self) -> bool:
        return time.monotonic() < self._synthetic_until

    @property
    def clipboard(self):
        if self._clipboard is None:
            self._clipboard = QtClipboard()
        return self._clipboard

    @property
    def input(self):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            raise NativeError("Global input needs an X11 session. Wayland input requires a compositor portal.")
        if self._input is None:
            try:
                self._input = PynputInput()
            except Exception as e:
                raise NativeError(f"Desktop input is unavailable: {e}") from None
        return self._input

    def capabilities(self) -> dict:
        accessible = not isinstance(self.backend, UnavailableAccessibility)
        wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
        return {"accessibility": accessible, "global_input": not wayland,
                "screen_capture": not wayland, "clipboard": True,
                "meeting_loopback": sys.platform == "win32" or sys.platform.startswith("linux"),
                "calendar": False, "contacts": False,
                "detail": getattr(self.backend, "reason", "") or
                ("Wayland needs screen/input portals; use X11 for global controls." if wayland else "")}

    def poll_focus(self) -> None:
        try:
            reader = (self.backend.focus if self._corrections.active else
                      getattr(self.backend, "focus_metadata", self.backend.focus))
            target = reader()
            if target and target.pid != os.getpid():
                self._external = replace(target, text="")
            self._corrections.poll(target)
        except Exception:
            pass

    def set_learning(self, on: bool) -> None:
        self._corrections.enable(on)

    def take_corrections(self) -> list[tuple[str, str]]:
        return self._corrections.take()

    def remember_focus(self) -> None:
        """Key down: which field the user is in. Metadata only (no field text), so the key stays instant."""
        self._dictation_return = None
        try:
            current = self._metadata()
        except Exception:
            current = None
        if current and current.pid != os.getpid():
            self._external = replace(current, text="")
        self._remembered = replace(current, text="") if current and current.pid != os.getpid() else self._external

    def _metadata(self) -> Focus | None:
        return getattr(self.backend, "focus_metadata", self.backend.focus)()

    def arm_return_to_dictation_target(self) -> None:
        """One explicit on-screen Finish may return from Milo to its captured field."""
        self._dictation_return = None
        target = self._remembered
        try:
            if writable(target) and self._milo_in_foreground():
                self._dictation_return = (target.identity, target.pid, time.monotonic() + 120)
        except Exception:
            pass  # A missing accessibility provider leaves the normal copy fallback.

    def _foreground_known(self) -> bool:
        """Does the OS name another app as the one in front? Without accessibility focus that's all we know."""
        try:
            front = getattr(self.backend, "foreground_pid", lambda: None)()
        except Exception:
            return False
        return front is not None and front != os.getpid()

    def _milo_in_foreground(self, current: Focus | None = None) -> bool:
        reader = getattr(self.backend, "foreground_pid", None)
        if reader is not None:
            return reader() == os.getpid()
        current = current or self.backend.focus()
        return bool(current and current.pid == os.getpid() and self._keyboard_target(current))

    def context(self) -> dict:
        target = self._metadata()
        try:
            idle = float(self.keys.idle_s())
        except Exception:
            idle = 0.0
        return {"app": target.app if target and target.pid != os.getpid() else None, "idle_s": idle}

    def _same(self, expected: Focus | None, actual: Focus | None) -> bool:
        return bool(expected and actual and expected.identity == actual.identity and expected.pid == actual.pid)

    def _keyboard_target(self, target: Focus) -> bool:
        return bool(getattr(self.backend, "keyboard_focus_matches", lambda _: True)(target))

    def _inject(self, operation, *args):
        self._synthetic_until = time.monotonic() + 0.35
        try:
            return operation(*args)
        finally:
            self._synthetic_until = time.monotonic() + 0.2

    def _paste_keys(self) -> None:
        self._inject(self.keys.paste_keys)

    def _type(self, text: str) -> bool:
        """Terminals (Claude Code in Windows Terminal) keep Ctrl+V for their own paste and may drop it, but take typed
        keys. One line only: a typed line break would run it. False when the platform can't type, so it pastes."""
        if "\n" in text or not hasattr(self.keys, "type_text"):
            return False
        try:
            return bool(self._inject(self.keys.type_text, text))
        except NativeError:
            return False

    def _paste_blind(self, text: str, current: Focus | None) -> dict:
        """Ctrl+V into whatever has the keyboard focus, as the Mac does for dictation: Chrome before its
        accessibility tree wakes, Electron apps and canvases don't report a writable field, but take a paste."""
        if current is not None and _TERMINAL.search(current.app) and self._type(text):
            return {"pasted": True, "field": "", "app": current.app, "typed": True}
        snapshot = self.clipboard.snapshot()
        self.clipboard.set_text(text)
        try:
            self._paste_keys()
        except NativeError as error:
            getattr(self.clipboard, "keep", lambda _: None)(text)  # the words stay for the user's own Ctrl+V
            return {"pasted": False, "why": "blocked", "error": str(error)}
        except Exception:
            self.clipboard.restore_later(snapshot, text)
            raise
        self.clipboard.restore_later(snapshot, text)
        return {"pasted": True, "field": "", "app": current.app if current else ""}

    def _paste(self, text: str, target: Focus, *, spacing: bool = False) -> dict:
        current = self.backend.focus()
        if not writable(current) or not self._same(target, current) or not self._keyboard_target(current):
            return {"pasted": False, "why": "moved"}
        before = current.text
        try:
            selected = getattr(self.backend, "selection_span", lambda _: None)(current)
        except Exception:
            selected = None
        if (selected is not None and len(selected) == 2 and 0 <= selected[0] <= selected[1] <= len(before)
                and selected[1] - selected[0] <= 4096):
            offset, end = selected
            if spacing:
                text = spaced(text, before[offset - 1] if offset else "")
        else:
            # Unknown selection: only an exactly verified append can be undone.
            offset = end = len(before)
        replaced = before[offset:end]
        after = before[:offset] + text + before[end:]
        snapshot = self.clipboard.snapshot()
        self.clipboard.set_text(text)
        # Re-read immediately before injecting: another window may have taken focus.
        if not self._same(current, self.backend.focus()) or not self._keyboard_target(current):
            self.clipboard.restore_later(snapshot, text)
            return {"pasted": False, "why": "moved"}
        try:
            self._paste_keys()
        except NativeError as error:
            getattr(self.clipboard, "keep", lambda _: None)(text)
            return {"pasted": False, "why": "blocked", "error": str(error)}
        finally:
            self.clipboard.restore_later(snapshot, text)
        field = "field-" + uuid.uuid4().hex[:12]
        self._writes[field] = _Write(replace(current, text=""), hashlib.sha256(before.encode()).digest(),
                                    hashlib.sha256(after.encode()).digest(), text, offset, replaced)
        while len(self._writes) > 32:
            self._writes.pop(next(iter(self._writes)))
        return {"pasted": True, "field": field, "app": current.app, "text": text}

    def paste_dictation(self, text: str, *, learn: bool = True) -> dict:
        """Dictation goes where the keyboard focus is when the words arrive, as on the Mac. Refused: Milo's own
        window (unless the user finished from it, see `arm_return_to_dictation_target`), password fields and
        managers, a window Windows won't let Milo type into (elevated), and line breaks into a terminal, where
        they would run a command. A field Milo can verify also gets spacing, undo and corrections."""
        started = time.monotonic()
        result = self.write(text) if not learn else self._dictate(text)
        if learn and result.get("pasted") is False and result.get("why") not in ("empty", "secure"):
            self.clipboard.set_text(text)
            result["copied"] = True
        log.info("%s %d chars: %s%s in %s (%.0f ms)", "dictation" if learn else "write", len(text),
                 "pasted" if result.get("pasted") else "kept, " + str(result.get("why", "")),
                 " (verified field)" if result.get("field") else "", result.get("app") or "?",
                 (time.monotonic() - started) * 1000)
        return result

    def _dictate(self, text: str) -> dict:
        armed, self._dictation_return = self._dictation_return, None
        if not text:
            return {"pasted": False, "why": "empty"}
        # Ask the OS for the foreground PID first: AT-SPI can't query Milo's own Qt provider on this thread.
        if armed and self._milo_in_foreground():
            return self._return_and_paste(text, armed)
        try:
            current = self.backend.focus()
        except Exception:
            current = None
        try:
            if self._milo_in_foreground(current):
                return {"pasted": False, "why": "here"}
        except Exception:
            pass
        if current is None and not self._foreground_known():
            return {"pasted": False, "why": "no_field"}  # no idea where Ctrl+V would land
        if _secret(current):
            return {"pasted": False, "why": "secure"}
        if "\n" in text.strip() and (current is None or _TERMINAL.search(current.app)):
            return {"pasted": False, "why": "terminal"}
        blocked = self.keys.blocked(current.pid if current else None)
        if blocked:
            return {"pasted": False, "why": "elevated", "error": blocked}
        target = self._remembered
        if writable(current) and self._same(target, current) and self._keyboard_target(current):
            result = self._paste(text, current, spacing=True)
            if result.get("pasted"):
                self._corrections.pasted(current, result.pop("text", text))
                return result
            if result.get("why") != "moved":
                return result
            current = self.backend.focus()  # it moved under us: the words go where the focus is now
            if (_secret(current) or self._milo_in_foreground(current) or
                    (current is None and not self._foreground_known())):
                return {"pasted": False, "why": "moved"}
        return self._paste_blind(text, current)

    def _return_and_paste(self, text: str, armed: tuple[str, int, float]) -> dict:
        """The user pressed Finish in Milo's window: go back to the captured field, once, and only to it."""
        target = self._remembered
        if not writable(target):
            return {"pasted": False, "why": "secure" if target and target.secure else "no_field"}
        if not (armed[:2] == (target.identity, target.pid) and time.monotonic() < armed[2]):
            return {"pasted": False, "why": "moved"}
        try:
            refreshed = self.backend.refresh(target)
            if not writable(refreshed) or not self._same(target, refreshed) or refreshed.window != target.window:
                return {"pasted": False, "why": "moved"}
            self.backend.focus_field(refreshed)
            current = self.backend.focus()
        except Exception:
            return {"pasted": False, "why": "moved"}
        if not self._same(target, current) or not writable(current):
            return {"pasted": False, "why": "moved"}
        result = self._paste(text, target, spacing=True)
        if result.get("pasted"):
            self._corrections.pasted(current, result.pop("text", text))
        return result

    def write(self, text: str) -> dict:
        """text.write: what Milo wrote for the user goes only into the exact field that had the focus when the
        talk key went down (ADR 33, the Mac's PasteTarget). Anything else is kept in Milo's window to copy."""
        self._dictation_return = None
        if not text:
            return {"pasted": False, "why": "empty"}
        current = self.backend.focus()
        target = self._remembered
        if not writable(target):
            return {"pasted": False, "why": "secure" if target and target.secure else "no_field"}
        if not self._same(target, current) or not self._keyboard_target(current):
            return {"pasted": False, "why": "moved"}
        result = self._paste(text, target)
        result.pop("text", None)
        return result

    def app_request(self, op: str, args: dict) -> dict:
        if op == "text.copy":
            self.clipboard.set_text(str(args.get("text", "")))
            return {"copied": True}
        if op == "text.write":
            self._corrections.cancel()
            if not args.get("paste", True):
                return {"pasted": False, "why": "here"}
            return self.write(str(args.get("text", "")))
        if op == "text.unwrite":
            self._corrections.cancel()
            field = str(args.get("field", ""))
            record = self._writes.get(field)
            current = self.backend.focus()
            if not record or not writable(current) or not self._same(record.target, current):
                return {"removed": False, "why": "The field changed. Use the app's Undo instead."}
            inserted, offset = record.inserted, record.offset
            before = current.text[:offset] + record.replaced + current.text[offset + len(inserted):]
            if (inserted != args.get("text") or current.text[offset:offset + len(inserted)] != inserted or
                    hashlib.sha256(current.text.encode()).digest() != record.after_hash or
                    hashlib.sha256(before.encode()).digest() != record.before_hash):
                return {"removed": False, "why": "The text changed since. Use the app's Undo instead."}
            self.backend.set_value(current, before)
            self._writes.pop(field, None)
            return {"removed": True}
        if op in ("access.check", "access.request", "access.places"):
            need = str(args.get("need", "ui"))
            caps = self.capabilities()
            supported = caps.get({"ui": "accessibility", "control": "accessibility",
                                  "screen": "screen_capture", "contacts": "contacts"}.get(need, need), False)
            return {"access": "yes" if supported else "no", "app": str(args.get("app", "")),
                    "label": caps["detail"], "system": "Windows" if sys.platform == "win32" else "Linux"}
        if op == "platform.capabilities":
            return self.capabilities()
        raise NativeError(f"The {op} integration is not available on this desktop yet.")

    def _screenshot(self) -> dict:
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            raise NativeError("Screen capture needs a Wayland ScreenCast portal; use X11 for now.")
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QGuiApplication
        current = self.backend.focus()
        x, y, width, height = current.rect if current else (0, 0, 0, 0)
        screen = QGuiApplication.screenAt(QPoint(x + width // 2, y + height // 2)) or QGuiApplication.primaryScreen()
        if screen is None:
            raise NativeError("No desktop screen is available.")
        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            raise NativeError("The desktop did not permit this screenshot.")
        directory = self.home / "state" / "screens"
        directory.mkdir(parents=True, exist_ok=True)
        from milo import system
        system.make_private(directory, 0o700)
        path = directory / (uuid.uuid4().hex + ".png")
        if not pixmap.save(str(path), "PNG"):
            raise NativeError("The screenshot could not be saved.")
        system.make_private(path, 0o600)
        geometry, ratio = screen.geometry(), pixmap.devicePixelRatio()
        self._shot = (geometry.x(), geometry.y(), pixmap.width(), pixmap.height(), ratio)
        return {"image": str(path), "width": pixmap.width(), "height": pixmap.height()}

    def capture(self, mode: str = "window") -> dict:
        result = {}
        try:
            target = self.backend.focus()
            if target and not target.secure and not _SECRET_APP.search(target.app):
                result.update(app=target.app, window=target.window_title or target.title, focused=target.role)
                if mode == "selection":
                    result["selection"] = self.backend.selected_text(target)
                result["text"] = "\n".join(t.title + (": " + t.text if t.text else "")
                                               for t in self.backend.elements() if not t.secure)[:16000]
            elif target and (target.secure or _SECRET_APP.search(target.app)):
                return {"error": "Milo does not read password fields or password managers."}
            result["image"] = self._screenshot()["image"]
        except Exception as e:
            result["error"] = str(e)
        return result

    def session_event(self, event: dict) -> None:
        if event.get("type") == "hands_borrow":
            what = str(event.get("what", ""))
            if event.get("on"):
                self._borrowed[what] = time.monotonic() + 1.5
            else:
                self._borrowed.pop(what, None)
        elif event.get("type") == "hands_session" and not event.get("on"):
            self._borrowed.clear()
            self._checked = None
        elif event.get("type") == "meeting_status" and self._meeting_recorder is not None:
            self._meeting_recorder.pause(event.get("phase") == "paused")

    def meeting_record(self, event: dict, send) -> None:
        if self._meeting_recorder is None:
            from .meeting_audio import MeetingRecorder
            self._meeting_recorder = MeetingRecorder(self.home, send)
        self._meeting_recorder.record(event)

    def pause_meeting(self, on: bool) -> None:
        if self._meeting_recorder is not None:
            self._meeting_recorder.pause(on)

    def close(self) -> None:
        from .platform import end_diagnostics
        end_diagnostics(self.home)
        self._corrections.enable(False)
        self._writes.clear()
        self._remembered = self._external = None
        self._dictation_return = None
        if self._meeting_recorder is not None:
            self._meeting_recorder.close()
            # Flush the recorder's queued chunks/off notification while the wire
            # connection still exists. Do not pump arbitrary UI/input events.
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.MetaCall)

    def _borrow(self, device: str) -> None:
        if self._borrowed.get(device, 0) <= time.monotonic():
            raise BorrowRequired(device)
        self._borrowed[device] = time.monotonic() + 1.5

    def _point(self, args: dict) -> tuple[int, int]:
        if self._shot is None:
            raise NativeError("Take a screenshot before using its coordinates.")
        x, y = int(args["x"]), int(args["y"])
        left, top, width, height, ratio = self._shot
        if not 0 <= x < width or not 0 <= y < height:
            raise NativeError("The point is outside the last screenshot.")
        return round(left + x / ratio), round(top + y / ratio)

    def _target(self, tool: str, args: dict) -> Focus | None:
        if tool in ("ax_press", "ax_set_value"):
            target = self._elements.get(str(args.get("element", "")))
            if target is None:
                raise NativeError("That element id expired. Read the accessibility tree again.")
            if hasattr(self.backend, "refresh"):
                target = self.backend.refresh(target)
                if target is None:
                    raise NativeError("That control disappeared. Read the accessibility tree again.")
            return target
        if tool in ("click", "scroll") and "x" in args and "y" in args:
            return self.backend.at_point(*self._point(args))
        return self.backend.focus()

    def _describe(self, args: dict) -> dict:
        tool = str(args.get("tool", ""))
        if tool in ("open_app", "open_url", "open_file"):
            return {"app": str(args.get("name") or args.get("app") or "")}
        target = self._target(tool, args)
        if tool in ("type", "key"):
            self._checked = target
        if target is None:
            return {"unresolved": True, "app": ""}
        x, y, width, height = target.rect
        wx, wy, ww, wh = target.window_rect or target.rect
        return {"app": target.app, "title": target.title, "role": target.role, "secure": target.secure,
                "milo": target.pid == os.getpid(), "pid": target.pid,
                "window": {"x": wx, "y": wy, "width": ww, "height": wh},
                "point": {"x": x + width / 2, "y": y + height / 2}}

    def hands_request(self, tool: str, args: dict) -> dict:
        if tool in ("ax_set_value", "type", "key", "click", "ax_press", "run_script", "run_applescript"):
            self._corrections.cancel()
        if tool in ("sheet_write", "sheet_read", "write_document"):
            if self._office_tools is None:
                from ._office import OfficeTools
                self._office_tools = OfficeTools(self.home)
            return self._office_tools.run(tool, args)
        if tool == "describe" and args.get("tool") in ("sheet_write", "sheet_read", "write_document"):
            if self._office_tools is None:
                from ._office import OfficeTools
                self._office_tools = OfficeTools(self.home)
            return self._office_tools.describe(str(args["tool"]), {k: v for k, v in args.items() if k != "tool"})
        if tool == "describe":
            return self._describe(args)
        if tool == "focus_app":
            target = self.backend.activate(str(args.get("app", "")))
            actual = self.backend.focus()
            return {"app": target.app, "front": bool(actual and actual.pid == target.pid and self._keyboard_target(actual))}
        if tool == "list_apps":
            focus = self.backend.focus()
            return {"text": "\n".join(f"{target.app}: {target.title}" +
                    (" (in front)" if focus and focus.pid == target.pid else "")
                    for target in self.backend.windows())}
        if tool == "open_url":
            return self._open_url(str(args.get("url", "")), str(args.get("app", "")))
        if tool == "open_app":
            from ._native_opening import application_name
            name = application_name(str(args.get("name", "")))
            try:
                target = self.backend.activate(name)
                return {"app": target.app, "text": f"Opened {target.app}."}
            except NativeError:
                command = self._application(name)
                from ._native_opening import ApplicationCatalog
                subprocess.Popen(command, cwd=Path.home(), env=ApplicationCatalog(self.home).environment(), stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {"app": name, "text": f"Started {name}."}
        if tool == "open_file":
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            from ._native_opening import data_file
            path = data_file(Path(str(args.get("path", ""))))
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise NativeError("The file could not be opened.")
            return {"text": f"Opened {path.name}."}
        if tool == "screenshot":
            return self._screenshot()
        if tool in ("window_text", "ax_tree", "ax_find"):
            targets = self.backend.elements(str(args.get("app", "")))
            self._elements = {f"e{index}": target for index, target in enumerate(targets)
                              if not target.secure and target.pid != os.getpid()}
            if tool == "window_text":
                text = "\n".join(t.title + (": " + t.text if t.text else "") for t in self._elements.values())
            else:
                text = "\n".join(f"{identifier} {target.role} {target.title}" for identifier, target in self._elements.items()
                                 if str(args.get("text", "")).casefold() in target.title.casefold() and
                                 str(args.get("role", "")).casefold() in target.role.casefold())
            return {"text": text[:16000], "summary": "A bounded live accessibility snapshot; element ids expire on the next tree."}
        if tool in ("ax_press", "ax_set_value", "type", "key", "click", "scroll"):
            target = self._target(tool, args)
            if target is None or target.secure or target.pid == os.getpid() or _SECRET_APP.search(target.app):
                raise NativeError("Milo cannot act on this field or window.")
            if tool == "ax_press":
                self.backend.press(target)
            elif tool == "ax_set_value":
                self.backend.set_value(target, str(args.get("text", "")))
            elif tool == "type":
                if not writable(target) or not self._same(self._checked, target):
                    raise NativeError("The focused text field changed or is unsafe. Read it again.")
                self._borrow("keyboard")
                if not self._paste(str(args.get("text", "")), target).get("pasted"):
                    raise NativeError("The focused field changed before typing.")
            elif tool == "key":
                if _TERMINAL.search(target.app):
                    raise NativeError("Milo does not inject keys into terminals or command editors.")
                if not self._same(self._checked, target):
                    raise NativeError("The focused control changed. Read it again.")
                if not self._keyboard_target(target):
                    raise NativeError("The target app no longer has keyboard focus.")
                self._borrow("keyboard")
                self._inject(self.input.shortcut, str(args.get("combo", "")))
            elif tool == "click":
                self._borrow("mouse")
                self._inject(self.input.click, *self._point(args), str(args.get("button", "left")), bool(args.get("double")))
            elif tool == "scroll":
                self._borrow("mouse")
                point = self._point(args) if "x" in args and "y" in args else None
                self._inject(self.input.scroll, int(args.get("dx", 0)), int(args.get("dy", 0)), point)
            return {"text": "Done.", "app": target.app}
        raise NativeError(f"The {tool} action needs a platform adapter that is not installed.")

    hands = hands_request

    def _open_url(self, url: str, app: str) -> dict:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or any(ord(c) < 32 for c in url):
            raise NativeError("Only a complete http or https address can be opened.")
        if app:
            from ._native_opening import ApplicationCatalog
            command = ApplicationCatalog(self.home).command(app, browser=True)
            subprocess.Popen([*command, url], cwd=Path.home(), env=ApplicationCatalog(self.home).environment(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            if not QDesktopServices.openUrl(QUrl(url)):
                raise NativeError("The default browser could not open this address.")
        return {"app": app or "browser", "text": f"Opened {parsed.netloc}."}

    def _application(self, name: str) -> list[str]:
        from ._native_opening import ApplicationCatalog
        return ApplicationCatalog(self.home).command(name)
