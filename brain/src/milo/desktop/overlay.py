"""Keeps the floating Milo's window honest with the screen: clicks go through it except where he and his surfaces are
(`PresenceWindow.inputRegion` as the window's mask), and his eyes get the pointer while he is on screen.

The mask is also the drawn area on some platforms (Windows clips painting to it), so each rectangle is padded for
the soft shadows around it. It also puts the window in the bottom-right corner of the screen you're working on, as
the Mac's OverlayPanel.placeBottomRight does with NSScreen.main.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QPoint, QPointF, QRect, QSize, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QRegion

log = logging.getLogger("milo.desktop.overlay")

# 30 times a second while he is on screen: enough for eyes that move in 16 steps; nothing while he is away.
TICK_MS = 33
# The shadow under a surface reaches this far past it (FloatingSurface: blur 24 × 0.7, 5 down).
SHADOW = 24
# After he leaves, the window hides once the way off has played (PresenceWindow's 0.78 s flight).
GONE_MS = 900
# Clear of the screen's edge, like the Mac's 8 pt.
EDGE = 8


def corner(available: QRect, size: QSize, edge: int = EDGE) -> QPoint:
    """Where the window goes: the bottom-right of a screen's available area (taskbar excluded)."""
    return QPoint(available.right() + 1 - size.width() - edge, available.bottom() + 1 - size.height() - edge)


def region(rects, pad: int = SHADOW) -> QRegion:
    """The union of `rects` (QRectF or QRect), each grown by `pad`; a single pixel when there is none, since an empty
    mask means no mask at all."""
    area = QRegion()
    if hasattr(rects, "toVariant"):  # a QML list property arrives as a QJSValue
        rects = rects.toVariant()
    for rect in rects or []:
        r = rect.toRect() if hasattr(rect, "toRect") else QRect(rect)
        area = area.united(QRegion(r.adjusted(-pad, -pad, pad, pad)))
    return area if not area.isEmpty() else QRegion(QRect(0, 0, 1, 1))


class OverlayTracker(QObject):
    def __init__(self, window, presence, parent=None):
        super().__init__(parent)
        self.window, self.presence = window, presence
        self._mask: QRegion | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)
        presence.shownChanged.connect(self._shown)
        app = QGuiApplication.instance()
        app.screenAdded.connect(lambda *_: self.place())
        app.screenRemoved.connect(lambda *_: self.place())
        self.place()
        self._shown()

    def place(self) -> None:
        """Into the corner of the screen under the pointer (where the user works), else the primary one."""
        app = QGuiApplication.instance()
        screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
        if screen is not None:
            self.window.setPosition(corner(screen.availableGeometry(), self.window.size()))

    def _shown(self) -> None:
        if self.presence.shown:
            # A window that was hidden comes back with a fresh expose. Masking it down to nothing instead left Windows
            # thinking it covered, and Qt stopped drawing it: back on screen but blank after a long absence.
            if not self.window.isVisible():
                self.window.show()
            self.place()
            self._timer.start()
            self.tick()
        else:
            self._timer.stop()
            self.presence.set_cursor(None)
            QTimer.singleShot(GONE_MS, self._gone)
        log.info("milo %s at %s", "shown" if self.presence.shown else "away", self.window.position())

    def _gone(self) -> None:
        """Once his flight off the screen has played: no window at all, so nothing to click and nothing to draw."""
        if not self.presence.shown:
            self.window.hide()
            log.info("milo's window hidden")

    def tick(self) -> None:
        position = QCursor.pos()
        self.presence.set_cursor(QPointF(position))
        self.apply_mask()

    def apply_mask(self) -> None:
        mask = region(self.window.property("inputRegion"))
        if mask != self._mask:
            self._mask = mask
            self.window.setMask(mask)
            log.debug("mask %s", mask.boundingRect())
