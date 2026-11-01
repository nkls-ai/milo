"""`presence`: what the floating Milo, his bubble and the voice capsule show (Presence/PresenceWindow.qml binds it).

Each property has its own notify signal and is emitted only when its value really changed. The level and the
bubble's word reveal change many times a second and touch nothing else.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, QTimer, Signal, Slot

from ..model import confirmation_answer
from ..presentation.clock import monotonic
from ..presentation.milo import COPIED, MiloState
from ..presentation.presence import Presence, hide_after
from ._qt import QtScheduler, field, readonly

REVEAL_FPS = 30
# Idle this long and Milo dozes when nothing is going on (MiloController.Settings.drowsyAfter on the Mac).
DROWSY_AFTER = 600.0


class PresenceViewModel(QObject):
    phaseChanged = Signal()
    modeChanged = Signal()
    colorModeChanged = Signal()
    handsFreeChanged = Signal()
    stateChanged = Signal()
    emotionChanged = Signal()
    levelChanged = Signal()
    bubbleChanged = Signal()
    bubbleActionChanged = Signal()
    revealChanged = Signal()
    heardChanged = Signal()
    partialChanged = Signal()
    speakingChanged = Signal()
    connectedChanged = Signal()
    helpersActiveChanged = Signal()
    helpersChanged = Signal()
    hintChanged = Signal()
    spokenChanged = Signal()
    shownChanged = Signal()
    canStopChanged = Signal()
    questionChanged = Signal()
    lookingChanged = Signal()
    cursorChanged = Signal()
    drowsyChanged = Signal()
    recordingChanged = Signal()

    celebrate = Signal()
    nudge = Signal()
    # What the overlay's own buttons ask for; the controller acts on them.
    openRequested = Signal()
    stopRequested = Signal()
    cancelRequested = Signal()
    setupRequested = Signal()
    copyRequested = Signal(str)
    command = Signal(dict)

    def __init__(self, scheduler=None, clock=monotonic, parent=None):
        super().__init__(parent)
        scheduler = scheduler or QtScheduler()
        self.model = MiloState(scheduler, clock, self._changed)
        self.model.on_celebrate = self.celebrate.emit
        self.model.on_nudge = self.nudge.emit
        self.presence = Presence(scheduler, lambda: self.model.needed, lambda shown: self.shownChanged.emit())
        self._values = self._snapshot()
        self._reveal = {"shown": 0, "fresh": 0, "alpha": 1.0}
        self._cursor: QPointF | None = None
        self._drowsy = False
        self._ticker = QTimer(self)
        self._ticker.setInterval(1000 // REVEAL_FPS)
        self._ticker.timeout.connect(self._tick)

    # ---- what QML reads

    phase = field(str, "phase", phaseChanged)
    mode = field(str, "mode", modeChanged)
    colorMode = field(str, "colorMode", colorModeChanged)
    handsFree = field(bool, "handsFree", handsFreeChanged)
    state = field(str, "state", stateChanged)
    emotion = field(str, "emotion", emotionChanged)
    bubble = field(str, "bubble", bubbleChanged)
    bubbleAction = field("QVariantMap", "bubbleAction", bubbleActionChanged)
    heard = field(str, "heard", heardChanged)
    partial = field(str, "partial", partialChanged)
    speaking = field(bool, "speaking", speakingChanged)
    connected = field(bool, "connected", connectedChanged)
    helpersActive = field(bool, "helpersActive", helpersActiveChanged)
    helpers = field("QVariantList", "helpers", helpersChanged)
    hint = field(str, "hint", hintChanged)
    spoken = field(str, "spoken", spokenChanged)
    canStop = field(bool, "canStop", canStopChanged)
    question = field("QVariantMap", "question", questionChanged)
    looking = field(bool, "looking", lookingChanged)
    recording = field(bool, "recording", recordingChanged)
    level = readonly(float, lambda self: self.model.level, levelChanged)
    shown = readonly(bool, lambda self: self.presence.shown, shownChanged)
    # {shown, fresh, alpha}: characters of `bubble` shown in full, then a word fading in (SpeechReveal).
    reveal = readonly("QVariantMap", lambda self: self._reveal, revealChanged)
    # The pointer in screen coordinates while Milo is on screen, for his eyes; null when unknown (OverlayTracker).
    cursor = readonly("QVariant", lambda self: self._cursor, cursorChanged)
    # The user has been away from the keyboard and mouse a while: idle and quiet, he dozes.
    drowsy = readonly(bool, lambda self: self._drowsy, drowsyChanged)

    def _snapshot(self) -> dict:
        m = self.model
        phase = m.voice_phase
        return {
            "phase": phase.kind if phase else "",
            "mode": phase.mode if phase else "",
            "colorMode": phase.color_mode if phase else "",
            "handsFree": bool(phase and phase.hands_free),
            "recording": bool(phase and phase.recording),
            "spoken": phase.spoken if phase else "",
            "state": m.state,
            "emotion": m.emotion,
            "bubble": m.bubble,
            "bubbleAction": dict(m.bubble_action or {}),
            "heard": m.heard,
            "partial": m.partial,
            "speaking": m.state == "speaking",
            "connected": m.connected,
            "helpersActive": m.helpers_active,
            "helpers": list(m.helpers),
            "hint": m.hint,
            "canStop": m.can_stop,
            "question": dict(m.question or {}),
            "looking": m.looking,
        }

    def _changed(self, names: set[str]) -> None:
        if names == {"level"}:
            self.levelChanged.emit()
            return
        if "level" in names:
            self.levelChanged.emit()
        before, self._values = self._values, self._snapshot()
        for key, value in self._values.items():
            if before.get(key) != value:
                getattr(self, key + "Changed").emit()
        if "reveal" in names:
            self._tick()
        self.presence.check()

    def _tick(self) -> None:
        cut = self.model.reveal.cut(self.model.now())
        reveal = {"shown": cut.shown, "fresh": cut.fresh, "alpha": round(cut.alpha, 3)}
        if reveal != self._reveal:
            self._reveal = reveal
            self.revealChanged.emit()
        done = self.model.reveal.done(self.model.now())
        if done and self._ticker.isActive():
            self._ticker.stop()
        elif not done and not self._ticker.isActive():
            self._ticker.start()

    # ---- fed by the controller

    def apply(self, event: dict) -> None:
        self.model.apply(event)
        if event.get("type") == "settings":
            for setting in event.get("settings") or []:
                if setting.get("section") == "ui" and setting.get("key") == "hide_after_s":
                    self.presence.hide_after = hide_after(setting.get("value"))

    def set_connected(self, up: bool) -> None:
        self.model.set_connected(up)

    def ear(self, kind: str, mode: str) -> None:
        self.model.ear_event(kind, mode)
        if kind == "armed":
            # Back on screen even if this turns out to be a tap: the key is the user asking for him.
            self.presence.summon()

    def set_cursor(self, point: QPointF | None) -> None:
        if point != self._cursor:
            self._cursor = point
            self.cursorChanged.emit()

    def set_idle(self, seconds: float) -> None:
        drowsy = seconds > DROWSY_AFTER
        if drowsy != self._drowsy:
            self._drowsy = drowsy
            self.drowsyChanged.emit()

    def set_hands_free(self, mode: str) -> None:
        self.model.set_hands_free(mode or None)

    def pasted(self, text: str) -> None:
        self.model.pasted_text(text)

    def offer_copy(self, text: str) -> None:
        self.model.offer_copy(text)

    # ---- what the overlay's buttons call

    @Slot()
    def openWindow(self) -> None:
        self.presence.summon()
        self.openRequested.emit()

    @Slot()
    def stop(self) -> None:
        self.stopRequested.emit()

    @Slot()
    def cancel(self) -> None:
        self.cancelRequested.emit()

    @Slot()
    def summon(self) -> None:
        self.presence.summon()

    @Slot()
    def dismiss(self) -> None:
        self.presence.dismiss()

    @Slot(bool)
    def setHeld(self, held: bool) -> None:
        self.presence.held = held
        self.presence.check()

    @Slot(bool)
    def setPointing(self, pointing: bool) -> None:
        self.presence.pointing = (lambda: True) if pointing else (lambda: False)

    @Slot(str)
    def answer(self, choice: str) -> None:
        """Yes, No, Allow always or a choice of the question's own, from a real click only."""
        question = self.model.question
        if not question:
            return
        try:
            message = confirmation_answer(question, choice)
        except ValueError:
            return
        self.model.answered()
        self.command.emit(message)

    @Slot()
    def performBubbleAction(self) -> None:
        action = self.model.bubble_action or {}
        kind = action.get("kind")
        if kind == "undo":
            self.command.emit({"type": "undo_task", "id": str(action.get("id", ""))})
        elif kind == "copy":
            self.copyRequested.emit(str(action.get("text", "")))
            self.model.show(COPIED)
        elif kind == "access":
            self.setupRequested.emit()
