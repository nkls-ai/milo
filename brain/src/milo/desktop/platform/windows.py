"""Windows: physical key state, Milo's own key injection, idle time and the UI Automation backend.

Every key Milo injects carries `MARKER` in `dwExtraInfo`, so the low-level hook drops exactly those events
(the Mac's PasteboardInserter.eventMarker), instead of guessing by time which keys were Milo's.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

MARKER = 0x4D696C6F  # "Milo"

VK = {"right_control": 0xA3, "right_option": 0xA5, "right_command": 0x5C,
      "ctrl": 0xA2, "alt": 0xA4, "cmd": 0x5B, "shift": 0xA0,
      "escape": 0x1B, "space": 0x20, "tab": 0x09, "enter": 0x0D}
_LCONTROL, _RCONTROL, _LMENU, _RMENU, _LSHIFT, _RSHIFT, _LWIN, _RWIN = 0xA2, 0xA3, 0xA4, 0xA5, 0xA0, 0xA1, 0x5B, 0x5C
_V = 0x56
_MASK = 0xE8  # unassigned: tells Windows an Alt or Win press was a chord, so its release opens no menu
_EXTENDED = {_RCONTROL, _RMENU, _LWIN, _RWIN}
_KEYEVENTF_EXTENDEDKEY, _KEYEVENTF_KEYUP, _KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):  # only to size the union like the real INPUT
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def code(name: str) -> int | None:
    if name in VK:
        return VK[name]
    if len(name) == 1 and name.isascii() and name.isalnum():
        return ord(name.upper())
    if name.startswith("vk:"):
        try:
            return int(name[3:])
        except ValueError:
            return None
    return None


class WindowsKeys:
    """The `KeyPlatform` for Windows. All calls are cheap and safe on the GUI thread."""

    polls = True  # GetAsyncKeyState sees keys even when Windows silently dropped a slow low-level hook

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
        self._user32.SendInput.restype = wintypes.UINT

    def _down(self, vk: int) -> bool:
        return bool(self._user32.GetAsyncKeyState(vk) & 0x8000)

    def is_down(self, name: str) -> bool | None:
        vk = code(name)
        return self._down(vk) if vk is not None else None

    def other_down(self, name: str) -> bool:
        """Is any key but `name` held? A voice key pressed inside a real shortcut is not a voice request."""
        vk = code(name)
        ignored = {vk, 0x10, 0x11, 0x12}  # generic Shift/Ctrl/Alt duplicate the side-specific codes
        if name == "right_option":
            ignored.add(_LCONTROL)  # AltGr's phantom left Control is not a user-held chord
        return any(self._down(other) for other in range(8, 256) if other not in ignored)

    def listener_options(self) -> dict:
        return {"win32_event_filter": self.event_filter}

    @staticmethod
    def event_filter(_message, data) -> bool:
        """False hides an event from Milo's own listener (Windows still delivers it to the apps)."""
        if (getattr(data, "dwExtraInfo", 0) or 0) == MARKER:
            return False  # Milo's own paste or menu mask
        # Physical AltGr adds a phantom left Control; its extended scan code identifies it.
        return not (data.vkCode == _LCONTROL and data.scanCode == 0x21D)

    def _send(self, keys: list[tuple[int, bool]]) -> None:
        if not keys:
            return
        inputs = (_INPUT * len(keys))()
        for item, (vk, down) in zip(inputs, keys):
            item.type = 1  # INPUT_KEYBOARD
            item.ki.wVk = vk
            item.ki.wScan = self._user32.MapVirtualKeyW(vk, 0) & 0xFF
            item.ki.dwFlags = (_KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0) | (0 if down else _KEYEVENTF_KEYUP)
            item.ki.dwExtraInfo = MARKER
        sent = self._user32.SendInput(len(keys), inputs, ctypes.sizeof(_INPUT))
        if sent != len(keys):
            from .ports import NativeError
            raise NativeError("Windows blocked Milo's key input (an elevated window may have the focus).")

    def paste_keys(self) -> None:
        """Ctrl+V with no stray modifier: held Alt, Shift or Win would make it a different shortcut (Ctrl+Alt+V
        is AltGr+V), so they are let go first; a Control the user still holds is used as it is, never released
        under them."""
        held = [vk for vk in (_LMENU, _RMENU, _LSHIFT, _RSHIFT, _LWIN, _RWIN) if self._down(vk)]
        ctrl = self._down(_LCONTROL) or self._down(_RCONTROL)
        keys = [(vk, False) for vk in held]
        if held and any(vk in (_LMENU, _RMENU, _LWIN, _RWIN) for vk in held):
            keys[:0] = [(_MASK, True), (_MASK, False)]  # the Alt/Win release must not open a menu
        keys += ([] if ctrl else [(_LCONTROL, True)]) + [(_V, True), (_V, False)] + ([] if ctrl else [(_LCONTROL, False)])
        self._send(keys)

    def type_text(self, text: str) -> bool:
        """Types `text` as Unicode key events: no clipboard and no shortcut, so a terminal app that keeps Ctrl+V
        for itself (Claude Code in Windows Terminal) still gets the words. False, typing nothing, while a modifier
        is held: Ctrl plus letters would be shortcuts."""
        if any(self._down(vk) for vk in (_LCONTROL, _RCONTROL, _LMENU, _RMENU, _LWIN, _RWIN)):
            return False
        units = text.encode("utf-16-le")
        codes = [int.from_bytes(units[i:i + 2], "little") for i in range(0, len(units), 2)]
        inputs = (_INPUT * (2 * len(codes)))()
        for index, code in enumerate(codes):
            for item, up in ((inputs[2 * index], 0), (inputs[2 * index + 1], _KEYEVENTF_KEYUP)):
                item.type = 1  # INPUT_KEYBOARD
                item.ki.wVk, item.ki.wScan = 0, code
                item.ki.dwFlags = _KEYEVENTF_UNICODE | up
                item.ki.dwExtraInfo = MARKER
        if self._user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT)) != len(inputs):
            from .ports import NativeError
            raise NativeError("Windows blocked Milo's key input (an elevated window may have the focus).")
        return True

    def mask_menu(self, name: str) -> None:
        """A held Alt or Win released alone opens the app's menu bar or Start; a masked press does not."""
        if name in ("right_option", "right_command", "alt", "cmd"):
            self._send([(_MASK, True), (_MASK, False)])

    def blocked(self, pid: int | None) -> str:
        """Why Windows would silently drop Milo's keys in `pid`'s window, or "" if it won't: an app running as
        administrator takes no input from an ordinary one (UIPI), and SendInput doesn't report it."""
        if not pid or _elevated(None):
            return ""
        if _elevated(pid):
            return ("That window runs as administrator, so Windows doesn't let Milo type into it. "
                    "Your words are on the clipboard: press Ctrl+V.")
        return ""

    def idle_s(self) -> float:
        class LastInput(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        info = LastInput()
        info.cbSize = ctypes.sizeof(info)
        if self._user32.GetLastInputInfo(ctypes.byref(info)):
            return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0
        return 0.0


def _elevated(pid: int | None) -> bool:
    """Is `pid` (None: this process) elevated? A process Milo may not even query counts as elevated."""
    kernel32, advapi32 = ctypes.windll.kernel32, ctypes.windll.advapi32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    process = kernel32.GetCurrentProcess() if pid is None else kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        return True
    token = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(process, 0x0008, ctypes.byref(token)):
            return True
        try:
            elevation, size = wintypes.DWORD(), wintypes.DWORD()
            if not advapi32.GetTokenInformation(token, 20, ctypes.byref(elevation), 4, ctypes.byref(size)):
                return False
            return bool(elevation.value)
        finally:
            kernel32.CloseHandle(token)
    finally:
        if pid is not None:
            kernel32.CloseHandle(process)


def accessibility():
    from .._native_windows import WindowsAccessibility
    return WindowsAccessibility()
