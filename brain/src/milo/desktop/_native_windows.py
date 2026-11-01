"""Windows UI Automation. COM patterns provide exact targets, including password/read-only checks."""
from __future__ import annotations

import os
import time
from pathlib import Path

from ._native_types import Focus, NativeError


class WindowsAccessibility:
    def __init__(self):
        import comtypes.client
        import win32gui
        import win32process
        import psutil

        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as uia
        self.uia = uia
        self.automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        try:
            bounded = self.automation.QueryInterface(uia.IUIAutomation2)
            bounded.ConnectionTimeout = 500
            bounded.TransactionTimeout = 800
        except Exception:
            pass  # older UIA providers do not expose timeout controls
        self.gui, self.process, self.psutil = win32gui, win32process, psutil

    def _name(self, pid: int) -> str:
        try:
            process = Path(self.psutil.Process(pid).name()).stem
            names = {"chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox",
                     "excel": "Microsoft Excel", "winword": "Microsoft Word", "powerpnt": "Microsoft PowerPoint",
                     "outlook": "Outlook", "explorer": "File Explorer", "notepad": "Notepad",
                     "code": "Visual Studio Code", "windowsterminal": "Windows Terminal",
                     "powershell": "PowerShell", "pwsh": "PowerShell"}
            return names.get(process.casefold(), process)
        except self.psutil.Error:
            return str(pid)

    def _pattern(self, element, kind: str):
        try:
            return element.GetCurrentPattern(getattr(self.uia, f"UIA_{kind}PatternId")).QueryInterface(
                getattr(self.uia, f"IUIAutomation{kind}Pattern"))
        except Exception:
            return None

    def _wrap(self, element, *, read_text=True) -> Focus | None:
        if not element:
            return None
        try:
            pid = int(element.CurrentProcessId)
            secure = bool(element.CurrentIsPassword)
            value = self._pattern(element, "Value") if not secure else None
            text = value.CurrentValue if value and read_text else ""
            if read_text and not text and not secure:
                pattern = self._pattern(element, "Text")
                if pattern:
                    text = pattern.DocumentRange.GetText(16000)
            rectangle = element.CurrentBoundingRectangle
            rect = (rectangle.left, rectangle.top, rectangle.right - rectangle.left,
                    rectangle.bottom - rectangle.top)
            type_id = element.CurrentControlType
            roles = {50000: "button", 50002: "checkbox", 50003: "combo box", 50004: "text field",
                     50005: "link", 50011: "menu item", 50020: "text", 50030: "document", 50032: "window"}
            editable = bool(type_id in (50003, 50004, 50030) and value and not value.CurrentIsReadOnly)
            if not editable and type_id in (50004, 50030) and not secure:
                text_pattern = self._pattern(element, "Text")
                # A document can be read-only. Only a Value pattern proves a writable field.
                editable = type_id == 50004 and bool(text_pattern)
                if type_id == 50030 and self._pattern(element, "TextEdit"):
                    editable = bool(element.CurrentIsEnabled)
            window = int(element.CurrentNativeWindowHandle or self.gui.GetForegroundWindow())
            window_title, window_rect = "", None
            try:
                import ctypes
                window = int(ctypes.windll.user32.GetAncestor(window, 2) or window)
                if self.process.GetWindowThreadProcessId(window)[1] == pid:
                    window_title = self.gui.GetWindowText(window)
                    left, top, right, bottom = self.gui.GetWindowRect(window)
                    window_rect = (left, top, right - left, bottom - top)
            except Exception:
                pass
            return Focus("uia:" + ":".join(str(v) for v in element.GetRuntimeId()), pid, self._name(pid),
                         str(window),
                         str(element.CurrentName or ""), roles.get(type_id, "control"), secure, editable,
                         str(text or "")[:16000], rect, element, window_title, window_rect)
        except Exception:
            return None

    def focus(self) -> Focus | None:
        return self._wrap(self.automation.GetFocusedElement())

    def foreground_pid(self) -> int | None:
        hwnd = self.gui.GetForegroundWindow()
        return self.process.GetWindowThreadProcessId(hwnd)[1] if hwnd else None

    def keyboard_focus_matches(self, target: Focus) -> bool:
        return self.foreground_pid() == target.pid and str(self.gui.GetForegroundWindow()) == target.window

    def focus_metadata(self) -> Focus | None:
        return self._wrap(self.automation.GetFocusedElement(), read_text=False)

    def refresh(self, target: Focus) -> Focus | None:
        current = self._wrap(target.handle)
        if current and current.identity == target.identity and current.pid == target.pid:
            # A background child often has no NativeWindowHandle. Retain the
            # captured top-level HWND rather than borrowing Milo's foreground HWND.
            try:
                if self.process.GetWindowThreadProcessId(int(target.window))[1] == target.pid:
                    from dataclasses import replace
                    current = replace(current, window=target.window, window_title=target.window_title,
                                      window_rect=target.window_rect)
            except Exception:
                return None
        return current

    def focus_field(self, target: Focus) -> Focus:
        current = self.refresh(target)
        hwnd = int(target.window)
        if (not current or current.identity != target.identity or current.pid != target.pid or
                not current.editable or current.secure or target.pid == os.getpid() or
                self.process.GetWindowThreadProcessId(hwnd)[1] != target.pid):
            raise NativeError("The captured dictation field is no longer available.")
        if self.process.GetWindowThreadProcessId(self.gui.GetForegroundWindow())[1] != os.getpid():
            raise NativeError("Another application has taken focus.")
        self._activate_hwnd(hwnd, target.app)
        checked = self.refresh(target)
        if (self.gui.GetForegroundWindow() != hwnd or not checked or checked.identity != target.identity or
                checked.pid != target.pid or checked.secure or not checked.editable):
            raise NativeError("The captured dictation field changed.")
        checked.handle.SetFocus()
        focused = self.focus()
        if (not focused or focused.identity != target.identity or focused.pid != target.pid or
                focused.secure or not focused.editable or self.gui.GetForegroundWindow() != hwnd):
            raise NativeError("The captured dictation field did not regain focus.")
        return focused

    def windows(self) -> list[Focus]:
        found = []
        def visit(hwnd, _):
            if self.gui.IsWindowVisible(hwnd) and self.gui.GetWindowText(hwnd):
                target = self._wrap(self.automation.ElementFromHandle(hwnd))
                if target and target.pid != os.getpid():
                    found.append(target)
        self.gui.EnumWindows(visit, None)
        return found

    def activate(self, app: str) -> Focus:
        wanted = app.casefold().removesuffix(".exe")
        matches = [w for w in self.windows() if wanted in (w.app.casefold(), w.title.casefold()) or
                   wanted in w.app.casefold() or wanted in w.title.casefold()]
        if not matches:
            raise NativeError(f"{app} has no open window. Open it first.")
        target = matches[0]
        hwnd = int(target.window)
        self._activate_hwnd(hwnd, app)
        return target

    def _activate_hwnd(self, hwnd: int, app: str) -> None:
        attached = False
        source_thread = foreground_thread = 0
        try:
            self.gui.ShowWindow(hwnd, 9)
            try:
                self.gui.SetForegroundWindow(hwnd)
            except Exception:
                # Windows may deny a background process's first activation.
                # Temporarily share the current input queue; always detach it.
                import ctypes
                import win32api
                source_thread = win32api.GetCurrentThreadId()
                foreground_thread = self.process.GetWindowThreadProcessId(self.gui.GetForegroundWindow())[0]
                if source_thread != foreground_thread:
                    attached = bool(ctypes.windll.user32.AttachThreadInput(source_thread, foreground_thread, True))
                self.gui.BringWindowToTop(hwnd)
                self.gui.SetForegroundWindow(hwnd)
        except Exception as e:
            raise NativeError(f"Windows did not bring {app} to the front: {e}") from None
        finally:
            if attached:
                import ctypes
                ctypes.windll.user32.AttachThreadInput(source_thread, foreground_thread, False)
        if self.gui.GetForegroundWindow() != hwnd:
            raise NativeError(f"Windows did not bring {app} to the front.")

    def elements(self, app: str = "") -> list[Focus]:
        if app:
            candidates = [w for w in self.windows() if app.casefold() in w.app.casefold() or
                          app.casefold() in w.title.casefold()]
            if not candidates:
                raise NativeError(f"No open window for {app}.")
            root = candidates[0].handle
        else:
            root = self.automation.ElementFromHandle(self.gui.GetForegroundWindow())
        walker = self.automation.ControlViewWalker
        result, pending = [], [(root, 0)]
        deadline = time.monotonic() + 0.9
        while pending and len(result) < 600 and time.monotonic() < deadline:
            element, depth = pending.pop()
            target = self._wrap(element)
            if target:
                result.append(target)
            if depth < 12:
                children = []
                try:
                    child = walker.GetFirstChildElement(element)
                    while child and len(children) < 150 and time.monotonic() < deadline:
                        children.append((child, depth + 1))
                        child = walker.GetNextSiblingElement(child)
                except Exception:
                    pass
                pending.extend(reversed(children))
        return result

    def at_point(self, x: int, y: int) -> Focus | None:
        from ctypes.wintypes import POINT
        return self._wrap(self.automation.ElementFromPoint(POINT(x, y)))

    def press(self, target: Focus) -> None:
        target = self.refresh(target)
        if target is None or target.secure:
            raise NativeError("Password fields cannot be controlled.")
        for kind, method in (("Invoke", "Invoke"), ("Toggle", "Toggle"), ("SelectionItem", "Select")):
            pattern = self._pattern(target.handle, kind)
            if pattern:
                getattr(pattern, method)()
                return
        raise NativeError("This control has no background action. Use its visible position instead.")

    def set_value(self, target: Focus, text: str) -> None:
        target = self.refresh(target)
        if target is None or target.secure or not target.editable:
            raise NativeError("This is not a writable, non-password field.")
        pattern = self._pattern(target.handle, "Value")
        if not pattern or pattern.CurrentIsReadOnly:
            raise NativeError("This field does not support setting text in the background.")
        pattern.SetValue(text)

    def selected_text(self, target: Focus) -> str:
        if target.secure:
            return ""
        pattern = self._pattern(target.handle, "Text")
        if pattern:
            ranges = pattern.GetSelection()
            if ranges and ranges.Length:
                return str(ranges.GetElement(0).GetText(16000))
        return ""

    def selection_span(self, target: Focus) -> tuple[int, int] | None:
        if target.secure or not target.editable:
            return None
        try:
            pattern = self._pattern(target.handle, "Text")
            if not pattern:
                return None
            ranges = pattern.GetSelection()
            if not ranges or ranges.Length != 1:
                return None
            selected = ranges.GetElement(0)
            prefix = pattern.DocumentRange.Clone()
            prefix.MoveEndpointByRange(1, selected, 0)  # End := selected.Start
            preceding, replacement = prefix.GetText(16001), selected.GetText(4097)
            start, end = len(preceding), len(preceding) + len(replacement)
            if target.text[:start] == preceding and target.text[start:end] == replacement and end <= len(target.text):
                return start, end
        except Exception:
            pass
        return None
