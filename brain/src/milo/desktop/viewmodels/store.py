"""`store`: the brain's lists as they came over the wire, for the pages (helpers, knowledge, routines, meetings,
settings, usage, Today). Each list has its own notify signal and is replaced only when its event arrives."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from ..model import DesktopState
from ._qt import readonly

# Which properties an event changes. The values are DesktopState attributes, read as they are.
TOUCHES = {
    "helpers": ("helpers",),
    "facts": ("facts",),
    "routines": ("routines", "drafts"),
    "settings": ("settings", "settingsRestart", "settingsError"),
    "meeting_status": ("meeting", "meetingLines", "meetingNotes"),
    "meeting_lines": ("meetingLines",),
    "meeting_notes": ("meetingNotes",),
    "usage": ("usage",),
    "remote": ("remote",),
    "reminders": ("reminders",),
    "undo_points": ("undoPoints",),
    "confirm": ("confirmations",),
    "confirm_done": ("confirmations",),
}
SOURCE = {"drafts": "drafts", "settingsRestart": "restart", "settingsError": "error", "meetingLines": "meeting_lines",
          "meetingNotes": "meeting_notes", "undoPoints": "undo_points"}


def _read(name: str):
    attribute = SOURCE.get(name, name)
    return lambda self: getattr(self.state, attribute)


class StoreViewModel(QObject):
    helpersChanged = Signal()
    factsChanged = Signal()
    routinesChanged = Signal()
    draftsChanged = Signal()
    settingsChanged = Signal()
    settingsRestartChanged = Signal()
    settingsErrorChanged = Signal()
    meetingChanged = Signal()
    meetingLinesChanged = Signal()
    meetingNotesChanged = Signal()
    usageChanged = Signal()
    remoteChanged = Signal()
    remindersChanged = Signal()
    undoPointsChanged = Signal()
    confirmationsChanged = Signal()
    # A done card for each `action_done`, newest last, for the Done cards by Milo and on Today.
    doneChanged = Signal()
    actionDone = Signal("QVariantMap")

    DONE_LIMIT = 12

    def __init__(self, state: DesktopState | None = None, parent=None):
        super().__init__(parent)
        self.state = state or DesktopState()
        self._done: list[dict] = []

    helpers = readonly("QVariantList", _read("helpers"), helpersChanged)
    facts = readonly("QVariantList", _read("facts"), factsChanged)
    routines = readonly("QVariantList", _read("routines"), routinesChanged)
    drafts = readonly("QVariantList", _read("drafts"), draftsChanged)
    settings = readonly("QVariantList", _read("settings"), settingsChanged)
    settingsRestart = readonly(bool, _read("settingsRestart"), settingsRestartChanged)
    settingsError = readonly(str, _read("settingsError"), settingsErrorChanged)
    meeting = readonly("QVariantMap", _read("meeting"), meetingChanged)
    meetingLines = readonly("QVariantList", _read("meetingLines"), meetingLinesChanged)
    meetingNotes = readonly("QVariantMap", _read("meetingNotes"), meetingNotesChanged)
    usage = readonly("QVariantMap", _read("usage"), usageChanged)
    remote = readonly("QVariantMap", _read("remote"), remoteChanged)
    reminders = readonly("QVariantList", _read("reminders"), remindersChanged)
    undoPoints = readonly("QVariantList", _read("undoPoints"), undoPointsChanged)
    # The questions waiting, oldest first, each the `confirm` event as sent.
    confirmations = readonly("QVariantList", lambda self: list(self.state.confirmations.values()), confirmationsChanged)
    done = readonly("QVariantList", lambda self: self._done, doneChanged)

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        touched = TOUCHES.get(kind)
        if kind == "action_done":
            card = {k: v for k, v in event.items() if k != "type"}
            self._done = (self._done + [card])[-self.DONE_LIMIT:]
            self.doneChanged.emit()
            self.actionDone.emit(card)
            return
        if touched is None:
            return
        self.state.apply(event)
        for name in touched:
            getattr(self, name + "Changed").emit()

    def lost(self) -> None:
        """The brain went away: its helpers and questions went with it."""
        self.apply({"type": "helpers", "helpers": []})
        for question in list(self.state.confirmations):
            self.apply({"type": "confirm_done", "id": question, "answer": "timeout"})
