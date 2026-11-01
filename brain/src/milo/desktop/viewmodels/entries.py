"""`entries`: the lines of the conversation the window shows, as a list model.

A streaming `reply_delta` changes one row (dataChanged on that index), a new line inserts one row, and only a
switch to another conversation resets the list, so the thread never lays itself out again while Milo talks.
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Property, QAbstractListModel, QByteArray, QModelIndex, Qt, Signal

from ..presentation import markdown, thread
from ..presentation.transcript import Change, Transcript

ROLES = ("entryId", "kind", "text", "html", "blocks", "time", "showTime", "day", "gap", "via", "viaIcon", "viaHelp",
         "mood", "done", "streaming", "written", "title", "status", "result", "steps", "files", "entry")


class EntriesModel(QAbstractListModel):
    countChanged = Signal()
    conversationChanged = Signal()
    # Something new at the end: the thread follows it unless the user scrolled back.
    grew = Signal()

    def __init__(self, transcript: Transcript, parent=None):
        super().__init__(parent)
        self.transcript = transcript
        self._live = True  # follows the conversation going on, through a split
        self._shown = ""
        self._rows: list[dict] = []
        self.today = date.today

    # ---- which conversation

    def show(self, conversation: str, *, live: bool) -> None:
        self._live = live
        target = self.transcript.current if live else conversation
        if target != self._shown or self._rows is not self.transcript.entries_of(target):
            self._reset(target)

    def changed(self, change: Change) -> None:
        """Called with every change the transcript reports."""
        if change.kind == "current":
            if self._live:
                self._reset(change.conversation)
            return
        if change.conversation != self._shown:
            return
        rows = self.transcript.entries_of(self._shown)
        if change.kind == "reset" or rows is not self._rows:
            self._reset(self._shown)
        elif change.kind == "insert":
            self.beginInsertRows(QModelIndex(), change.index, change.index)
            self.endInsertRows()
            self.countChanged.emit()
            self.grew.emit()
        elif change.kind == "update":
            at = self.index(change.index)
            self.dataChanged.emit(at, at)
            if change.index == len(rows) - 1:
                self.grew.emit()
        elif change.kind == "trim":
            self.beginRemoveRows(QModelIndex(), 0, change.index - 1)
            self.endRemoveRows()
            # The new first line has no line before it: its time, day and gap change.
            if rows:
                self.dataChanged.emit(self.index(0), self.index(0))
            self.countChanged.emit()

    def _reset(self, conversation: str) -> None:
        self.beginResetModel()
        changed = conversation != self._shown
        self._shown = conversation
        self._rows = self.transcript.entries_of(conversation)
        self.endResetModel()
        self.countChanged.emit()
        if changed:
            self.conversationChanged.emit()
        self.grew.emit()

    count = Property(int, lambda self: len(self._rows), notify=countChanged)
    conversation = Property(str, lambda self: self._shown, notify=conversationChanged)

    @property
    def rows(self) -> list[dict]:
        return self._rows

    # ---- the model

    def roleNames(self):
        return {Qt.ItemDataRole.UserRole + i: QByteArray(name.encode()) for i, name in enumerate(ROLES)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = ROLES[role - Qt.ItemDataRole.UserRole] if role >= Qt.ItemDataRole.UserRole else "text"
        row = index.row()
        entry = self._rows[row]
        previous = self._rows[row - 1] if row > 0 else None
        return self._role(name, entry, previous)

    def _role(self, name: str, entry: dict, previous: dict | None):
        kind = str(entry.get("kind", "milo"))
        if name == "entryId":
            return str(entry.get("id", ""))
        if name == "kind":
            return kind
        if name == "text":
            return str(entry.get("text", ""))
        if name == "html":
            # Escaped first: what the brain sends is text, never markup of its own.
            return markdown.inline(str(entry.get("text", "")))
        if name == "blocks":
            # Milo's lines with Markdown get laid out as blocks; plain lines stay one paragraph of prose.
            text = str(entry.get("text", ""))
            return markdown.parse(text) if kind == "milo" and markdown.has_markup(text) else []
        if name == "time":
            return thread.time_label(entry)
        if name == "showTime":
            return thread.shows_time(entry, previous)
        if name == "day":
            return thread.day_heading(entry, previous, self.today())
        if name == "gap":
            return thread.gap(entry, previous)
        if name in ("via", "viaIcon", "viaHelp"):
            via = str(entry.get("via", "voice"))
            icon, help_text = thread.VIA.get(via, thread.VIA["voice"])
            return {"via": via, "viaIcon": icon, "viaHelp": help_text}[name]
        if name == "mood":
            return thread.mood(entry)
        if name == "done":
            return bool(entry.get("done", True))
        if name == "streaming":
            return kind == "milo" and not entry.get("done", True)
        if name == "written":
            return bool(entry.get("written", False))
        if name in ("title", "status", "result"):
            return str(entry.get(name, ""))
        if name in ("steps", "files"):
            return list(entry.get(name) or [])
        return dict(entry)
