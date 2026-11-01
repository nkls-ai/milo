"""`conversations`: the sidebar's list and search, the shown conversation's header, and the moves between them
(ConversationsSidebar.swift, ConversationView.swift's keys). Commands go out through `command`."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from ..presentation import dates, sidebar
from ..presentation.transcript import Change, Transcript
from ._qt import field
from .entries import EntriesModel
from .navigation import RouteViewModel

SEARCH_DELAY_MS = 250  # ask a moment after the typing stops


class ConversationsViewModel(QObject):
    rowsChanged = Signal()
    currentChanged = Signal()
    moreChanged = Signal()
    searchChanged = Signal()
    resultsChanged = Signal()
    searchingChanged = Signal()
    headerChanged = Signal()
    liveChanged = Signal()
    remindersChanged = Signal()
    listChanged = Signal()
    revisionChanged = Signal()
    command = Signal(dict)

    def __init__(self, route: RouteViewModel, now: Callable[[], datetime] = datetime.now, parent=None):
        super().__init__(parent)
        self.now = now
        self.route = route
        self.transcript = Transcript(self._changed)
        self.entries = EntriesModel(self.transcript, self)
        self.meeting: dict = {}
        self._search = ""
        self._revision = 0
        self._values = self._snapshot()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(SEARCH_DELAY_MS)
        self._timer.timeout.connect(self._ask)
        route.moved.connect(self._moved)
        self._moved()

    rows = field("QVariantList", "rows", rowsChanged)
    # The brain's own list, as on the wire, for pages that show conversations (Today).
    list = field("QVariantList", "list", listChanged)
    current = field(str, "current", currentChanged)
    more = field(bool, "more", moreChanged)
    search = field(str, "search", searchChanged)
    results = field("QVariantList", "results", resultsChanged)
    # The search field has words, but the brain hasn't answered for exactly them yet: "Looking…".
    searching = field(bool, "searching", searchingChanged)
    header = field("QVariantMap", "header", headerChanged)
    # The page shows the conversation going on: the question bar, the drafts and "Going on" belong there.
    live = field(bool, "live", liveChanged)
    reminders = field("QVariantList", "reminders", remindersChanged)
    # Bumped on every change to the transcript, for bindings that read a task or an entry through a slot.
    revision = Property(int, lambda self: self._revision, notify=revisionChanged)

    def _shown(self) -> str:
        return self.route.conversation(self.transcript.current)

    def _snapshot(self) -> dict:
        t, now = self.transcript, self.now()
        shown = self._shown()
        info = t.info(shown) if shown else None
        query = self._search.strip()
        return {
            "rows": sidebar.rows(t.conversations, t.current, now, self.meeting),
            "list": list(t.conversations),
            "current": t.current,
            "more": t.more,
            "search": self._search,
            "results": sidebar.search_rows(t.search_results, now) if query and t.search_query == query else [],
            "searching": bool(query) and t.search_query != query,
            "header": sidebar.header(info, now) if info else {},
            "live": self.route.route.page.kind == "live" or (bool(shown) and shown == t.current),
            "reminders": list(t.reminders),
        }

    def _refresh(self) -> None:
        before, self._values = self._values, self._snapshot()
        for key, value in self._values.items():
            if before.get(key) != value:
                getattr(self, key + "Changed").emit()

    # ---- fed by the controller

    def apply(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "meeting_status":
            self.meeting = {k: v for k, v in event.items() if k != "type"}
            self._refresh()
            return
        self.transcript.apply(event)
        # A streamed word changes one row of the thread, nothing in the sidebar.
        if kind not in ("reply_delta", "activity", "entry"):
            self._refresh()

    def _changed(self, change: Change) -> None:
        self.entries.changed(change)
        self._revision += 1
        self.revisionChanged.emit()
        if change.kind == "current":
            self._refresh()

    def _moved(self) -> None:
        page = self.route.route.page
        if page.kind in ("live", "conversation"):
            self.entries.show(page.id, live=page.kind == "live")
        self._refresh()

    # ---- what the sidebar and the pages call

    @Slot(str)
    def open(self, conversation: str) -> None:
        """A row, a search hit or a task's way back to its conversation."""
        if conversation == self.transcript.current:
            self.route.go("live")
            return
        self.command.emit({"type": "open_conversation", "id": conversation})
        self.route.go("conversation", conversation)

    @Slot()
    def openFirst(self) -> None:
        results = self._values["results"]
        if results:
            self.open(results[0]["id"])

    @Slot(str, str)
    def rename(self, conversation: str, title: str) -> None:
        title = title.strip()
        info = self.transcript.info(conversation) or {}
        if title and title != info.get("title"):
            self.command.emit({"type": "rename_conversation", "id": conversation, "title": title})

    @Slot()
    def newConversation(self) -> None:
        self.command.emit({"type": "new_conversation"})
        self.route.go("live")

    @Slot()
    def older(self) -> None:
        oldest = min((dates.parse(c.get("last")) for c in self.transcript.conversations if dates.parse(c.get("last"))),
                     default=None)
        if oldest is not None:
            self.command.emit({"type": "get_conversations", "before": dates.wire(oldest)})

    @Slot(str)
    def setSearch(self, text: str) -> None:
        if text == self._search:
            return
        self._search = text
        if not text.strip():
            self._timer.stop()
            self.transcript.clear_search()
        else:
            self._timer.start()
        self._refresh()

    def _ask(self) -> None:
        query = self._search.strip()
        if query:
            self.command.emit({"type": "search_conversations", "query": query})

    @Slot(int)
    def step(self, by: int) -> None:
        """The conversation above or below the one shown, in the sidebar's order (Cmd/Ctrl+Alt+Up/Down)."""
        ids = [row["id"] for row in self._values["rows"]]
        if not ids:
            return
        shown = self._shown()
        at = ids.index(shown) if shown in ids else None
        target = min(max(at + by, 0), len(ids) - 1) if at is not None else (0 if by > 0 else len(ids) - 1)
        self.open(ids[target])

    @Slot(str)
    def openTask(self, task: str) -> None:
        """A helper's bird or a task card: its page, after asking for its conversation if the window lacks it."""
        if self.transcript.task(task) is None:
            owner = self.transcript.conversation_of_task(task)
            if owner is not None:
                self.command.emit({"type": "open_conversation", "id": owner["id"]})
        self.route.go("task", task)

    @Slot(str, result="QVariantMap")
    def task(self, task: str) -> dict:
        """A task's entry and the conversation that asked for it, for the task page; {} while unknown."""
        found = self.transcript.task(task)
        if found is None:
            owner = self.transcript.conversation_of_task(task)
            return {"loading": owner is not None}
        entry, info = found
        return {"entry": dict(entry), "conversation": dict(info or self.transcript.conversation_of_task(task) or {})}

    @Slot(str, result="QVariantList")
    def entriesOf(self, conversation: str) -> list:
        """A conversation's entries as the window has them, as on the wire (a meeting page's questions)."""
        return [dict(e) for e in self.transcript.entries_of(conversation or self.transcript.current)]

    @Slot(str, result="QVariantMap")
    def info(self, conversation: str) -> dict:
        return dict(self.transcript.info(conversation or self.transcript.current) or {})
