"""`working`: the frame and caption while Milo's hands work on screen (Presence/WorkingWindow.qml binds it)."""
from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, Signal

from ..presentation.milo import HANDS_STEP
from ._qt import readonly

STEP_LIMIT = 160


class WorkingViewModel(QObject):
    activeChanged = Signal()
    stepChanged = Signal()
    pointChanged = Signal()
    hasPointChanged = Signal()
    gestureChanged = Signal()
    clicksChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active, self._step, self._point = False, "", None
        self._gesture, self._clicks = "none", 0

    active = readonly(bool, lambda self: self._active, activeChanged)
    step = readonly(str, lambda self: self._step, stepChanged)
    # Where Milo points, in screen coordinates; (0, 0) with hasPoint false sends him home.
    point = readonly(QPointF, lambda self: self._point or QPointF(), pointChanged)
    hasPoint = readonly(bool, lambda self: self._point is not None, hasPointChanged)
    # What his pointer does (CursorView's gesture): "click" (a ripple), "typing" (a caret and his name) or "none";
    # `clicks` rises with each click, to ripple again.
    gesture = readonly(str, lambda self: self._gesture, gestureChanged)
    clicks = readonly(int, lambda self: self._clicks, clicksChanged)

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "hands_session":
            self._set_active(bool(event.get("on")))
        elif kind == "hands_request":
            self._hands(str(event.get("tool", "")), event.get("args") or {})
        elif kind == "fly_to":
            spot = event.get("point")
            try:
                point = QPointF(float(spot["x"]), float(spot["y"])) if spot else None
            except (KeyError, TypeError, ValueError):
                point = None
            if point != self._point:
                had, self._point = self._point is not None, point
                self.pointChanged.emit()
                if had != (point is not None):
                    self.hasPointChanged.emit()
        elif kind == "activity":
            step = event.get("step") or {}
            if str(step.get("id", "")).startswith(HANDS_STEP) and step.get("status") == "running":
                self._set_step(str(step.get("title", ""))[:STEP_LIMIT])

    def _hands(self, tool: str, args: dict) -> None:
        """The hands' own requests show on his pointer: a click ripples where it lands, keys show the caret."""
        if tool == "click":
            try:
                self.apply({"type": "fly_to", "point": {"x": float(args["x"]), "y": float(args["y"])}})
            except (KeyError, TypeError, ValueError):
                pass
            self._clicks += 1
            self.clicksChanged.emit()
            self._set_gesture("click")
        elif tool in ("type", "key", "text"):
            self._set_gesture("typing")
        else:
            self._set_gesture("none")

    def _set_gesture(self, gesture: str) -> None:
        if gesture != self._gesture:
            self._gesture = gesture
            self.gestureChanged.emit()

    def reset(self) -> None:
        self.apply({"type": "fly_to", "point": None})
        self._set_active(False)

    def _set_active(self, on: bool) -> None:
        if on != self._active:
            self._active = on
            self.activeChanged.emit()
        if not on:
            self._set_step("")
            self._set_gesture("none")

    def _set_step(self, text: str) -> None:
        if text != self._step:
            self._step = text
            self.stepChanged.emit()
