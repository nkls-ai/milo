"""`route`: which page the Milo window shows and the side it slides in from (WindowRoute.swift)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from ..presentation.route import Page, Route
from ._qt import readonly


class RouteViewModel(QObject):
    # One signal for the whole page: kind, id and direction change together, and a page transition reads all three.
    moved = Signal()
    sidebarShownChanged = Signal()

    def __init__(self, page: Page = Page("live"), parent=None):
        super().__init__(parent)
        self.route = Route(page)
        self._sidebar = False

    page = readonly(str, lambda self: self.route.page.kind, moved)
    pageId = readonly(str, lambda self: self.route.page.id, moved)
    # "today", "live", "conversation:c-1", "task:t-1": one key per page, for the page host's transitions.
    key = readonly(str, lambda self: ":".join(filter(None, (self.route.page.kind, self.route.page.id))), moved)
    forward = readonly(bool, lambda self: self.route.forward, moved)
    canGoBack = readonly(bool, lambda self: bool(self.route.back) or self.route.page.kind != "today", moved)
    sidebarShown = readonly(bool, lambda self: self._sidebar, sidebarShownChanged)

    @Slot(str)
    @Slot(str, str)
    def go(self, kind: str, page_id: str = "") -> None:
        if self.route.go(Page(kind, page_id)):
            self.moved.emit()
        self.setSidebarShown(False)

    @Slot()
    def back(self) -> None:
        if self.route.go_back():
            self.moved.emit()

    @Slot(bool)
    def setSidebarShown(self, shown: bool) -> None:
        if shown != self._sidebar:
            self._sidebar = shown
            self.sidebarShownChanged.emit()

    @Slot()
    def toggleSidebar(self) -> None:
        self.setSidebarShown(not self._sidebar)

    def conversation(self, current: str) -> str:
        return self.route.conversation(current)
