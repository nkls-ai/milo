"""The floating Milo's window takes clicks only where he is, his eyes get the pointer, and the hands' requests show on
his pointer."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtGui")

from PySide6.QtCore import QPointF, QRect, QRectF  # noqa: E402

from milo.desktop.overlay import region  # noqa: E402
from milo.desktop.viewmodels.presence import DROWSY_AFTER, PresenceViewModel  # noqa: E402
from milo.desktop.viewmodels.working import WorkingViewModel  # noqa: E402


def test_mask_is_his_rectangles_with_room_for_shadows():
    mask = region([QRectF(100, 100, 50, 40), QRect(10, 10, 5, 5)], pad=10)
    assert mask.contains(QRect(95, 95, 60, 50)) and not mask.contains(QRect(300, 300, 1, 1))
    # nothing of him: one pixel, never an empty mask (which would take every click)
    assert region([]).boundingRect() == QRect(0, 0, 1, 1)


def test_presence_tells_the_pointer_and_drowsiness_only_on_change():
    presence = PresenceViewModel()
    seen = []
    presence.cursorChanged.connect(lambda: seen.append("cursor"))
    presence.drowsyChanged.connect(lambda: seen.append("drowsy"))
    presence.set_cursor(QPointF(5, 5))
    presence.set_cursor(QPointF(5, 5))
    presence.set_idle(DROWSY_AFTER - 1)
    presence.set_idle(DROWSY_AFTER + 1)
    presence.set_idle(DROWSY_AFTER + 60)
    assert seen == ["cursor", "drowsy"]
    assert presence.drowsy and presence.cursor == QPointF(5, 5)


def test_hands_requests_move_and_ripple_his_pointer():
    working = WorkingViewModel()
    working.apply({"type": "hands_session", "on": True})
    working.apply({"type": "hands_request", "id": "h1", "tool": "click", "args": {"x": 640, "y": 412}})
    assert working.gesture == "click" and working.clicks == 1 and working.point == QPointF(640, 412)
    working.apply({"type": "hands_request", "id": "h2", "tool": "click", "args": {"x": 10, "y": 20}})
    assert working.clicks == 2
    working.apply({"type": "hands_request", "id": "h3", "tool": "type", "args": {"text": "hi"}})
    assert working.gesture == "typing"
    working.apply({"type": "hands_session", "on": False})
    assert working.gesture == "none"


def test_milo_sits_in_the_corner_of_the_screen_he_is_on_even_right_of_another_monitor():
    from PySide6.QtCore import QRect, QSize
    from milo.desktop.overlay import EDGE, corner
    # Two 1920×1080 screens side by side, a 48 px taskbar on each: the second starts at x 1920.
    right = corner(QRect(1920, 0, 1920, 1032), QSize(340, 380))
    assert (right.x(), right.y()) == (3840 - 340 - EDGE, 1032 - 380 - EDGE)
    left = corner(QRect(0, 0, 1920, 1032), QSize(340, 380))
    assert left.x() + 340 <= 1920, "never past the screen it belongs to"


def test_his_window_hides_after_he_leaves_and_shows_again_when_summoned():
    """Shrinking the window to nothing instead left it blank on Windows after a long absence (no fresh expose)."""
    from PySide6.QtCore import QCoreApplication, QSize
    from PySide6.QtGui import QWindow
    from milo.desktop import overlay
    from milo.desktop.overlay import OverlayTracker

    class Window(QWindow):  # the QML window's surface, without the scene
        def property(self, name):
            return [] if name == "inputRegion" else super().property(name)

    window, presence = Window(), PresenceViewModel()
    window.resize(QSize(340, 380))
    window.show()
    tracker = OverlayTracker(window, presence)
    original, overlay.GONE_MS = overlay.GONE_MS, 0
    try:
        presence.dismiss()
        for _ in range(5):
            QCoreApplication.processEvents()
        assert not presence.shown and not window.isVisible()
        presence.summon()
        assert presence.shown and window.isVisible()
    finally:
        overlay.GONE_MS = original
        tracker.deleteLater()
        window.destroy()
