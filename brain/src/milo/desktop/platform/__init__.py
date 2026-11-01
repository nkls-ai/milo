"""The desktop's OS boundary: Protocols in `ports`, one factory here choosing by OS.

    from milo.desktop.platform import create, create_hotkeys
    native = create(home)          # DesktopPlatform
    hotkeys = create_hotkeys()     # HotkeySource

The OS-specific pieces live in `windows.py` and `linux.py`; the shared policy (focus safety, paste, undo,
corrections) in `milo.desktop.native`, which only talks to an `Accessibility` backend and a `KeyPlatform`.
"""
from __future__ import annotations

from pathlib import Path

from .ports import (EAR_KINDS, BorrowRequired, Corrections, DesktopHands, DesktopPlatform, Focus, FocusTracker,
                    HotkeySource, MeetingAudio, NativeError, ScreenCapture, TextInserter)

__all__ = ["BorrowRequired", "Corrections", "DesktopHands", "DesktopPlatform", "EAR_KINDS", "Focus",
           "FocusTracker", "HotkeySource", "MeetingAudio", "NativeError", "ScreenCapture", "TextInserter",
           "combo_label", "create", "create_hotkeys", "diagnostics", "end_diagnostics", "key_label", "keys"]


def key_label(name: str) -> str:
    """A push-to-talk key as this OS's keyboard calls it: "Right Alt" on Windows/Linux, "Right Option" on a Mac."""
    from milo.adapters.platform import current
    from ..hotkeys import physical_key
    return current().key_names.key(physical_key(name))


def combo_label(combo: str) -> str:
    """A shortcut as this OS writes it: "Ctrl+Alt+M" on Windows/Linux, "Control-Option-M" on a Mac."""
    from milo.adapters.platform import current
    return current().key_names.combo(combo)


def keys():
    """The OS's key reading and injection helpers (`KeyPlatform`); see `windows.py`/`linux.py`."""
    import sys
    if sys.platform == "win32":
        from .windows import WindowsKeys
        return WindowsKeys()
    if sys.platform.startswith("linux"):
        from .linux import LinuxKeys
        return LinuxKeys()
    from .generic import GenericKeys
    return GenericKeys()


def create(home: Path, **options) -> DesktopPlatform:
    """The `DesktopPlatform` for this OS. Also starts `logs/desktop.log`: the voice path's health (keys, focus,
    paste outcomes), never the words or the keys typed."""
    diagnostics(Path(home))
    from ..native import NativeBridge
    return NativeBridge(home, **options)


def create_hotkeys(home: Path | None = None, parent=None) -> HotkeySource:
    from ..hotkeys import GlobalHotkeys
    hotkeys = GlobalHotkeys(parent=parent, keys=keys())
    if home is not None:
        hotkeys.set_diagnostics_path(Path(home) / "logs" / "hotkeys.json")
    return hotkeys


def diagnostics(home: Path) -> None:
    import logging
    from logging.handlers import RotatingFileHandler
    logger = logging.getLogger("milo.desktop")
    if any(getattr(handler, "_milo_desktop", False) for handler in logger.handlers):
        return
    try:
        (home / "logs").mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(home / "logs" / "desktop.log", maxBytes=1_000_000, backupCount=2,
                                      encoding="utf-8")
    except OSError:
        return
    handler._milo_desktop = True
    handler._milo_home = home
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def end_diagnostics(home: Path) -> None:
    """Close the log `diagnostics(home)` opened, so `home` can be removed (a temporary --diagnose home)."""
    import logging
    logger = logging.getLogger("milo.desktop")
    for handler in list(logger.handlers):
        if getattr(handler, "_milo_home", None) == Path(home):
            logger.removeHandler(handler)
            handler.close()
