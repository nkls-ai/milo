"""The tray icon and its menu: Open Milo, Connections & models…, Stop everything, Restart brain, Quit."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def icon() -> QIcon:
    for root in (Path(getattr(sys, "_MEIPASS", "")), Path(__file__).resolve().parents[4]):
        candidate = root / "assets" / "icon.png"
        if candidate.is_file():
            return QIcon(str(candidate))
    blank = QPixmap(32, 32)
    blank.fill()
    return QIcon(blank)


class Tray:
    def __init__(self, app, *, open_window: Callable[[], None], setup: Callable[[], None] | None,
                 stop: Callable[[], None], restart: Callable[[], None] | None, quit_app: Callable[[], None]):
        self.icon = QSystemTrayIcon(icon(), app)
        self.menu = QMenu()
        items = [("Open Milo", open_window), ("Connections & models…", setup), ("Stop everything", stop),
                 ("Restart brain", restart), None, ("Quit Milo", quit_app)]
        for item in items:
            if item is None:
                self.menu.addSeparator()
                continue
            title, action = item
            if action is None:
                continue
            entry = QAction(title, self.menu)
            entry.triggered.connect(action)
            self.menu.addAction(entry)
        self.icon.setContextMenu(self.menu)
        self.icon.setToolTip("Milo")
        self.icon.activated.connect(
            lambda reason: open_window() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def titles(self) -> list[str]:
        return [a.text() for a in self.menu.actions() if not a.isSeparator()]
