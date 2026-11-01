"""Where the Milo window is (MiloKit/WindowRoute.swift): the page, the way back, the side a page slides in from.

Pages: today, live (the conversation going on, following a split), conversation:<id>, task:<id>, usage, and the
desktop's own knowledge, routines, meetings and settings, which sit beside Today.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TOP = ("today", "usage", "knowledge", "routines", "helpers", "meetings", "settings")
DEPTH = {"live": 1, "conversation": 1, "task": 2}
BACK_LIMIT = 20


@dataclass(frozen=True)
class Page:
    kind: str = "today"
    id: str = ""

    @property
    def depth(self) -> int:
        return DEPTH.get(self.kind, 0)


@dataclass
class Route:
    page: Page = field(default_factory=Page)
    back: list[Page] = field(default_factory=list)
    forward: bool = True  # the last move went deeper: the page slides in from the right

    def go(self, page: Page) -> bool:
        if page == self.page:
            return False
        self.forward = page.depth >= self.page.depth
        self.back.append(self.page)
        del self.back[:-BACK_LIMIT]
        self.page = page
        return True

    def go_back(self) -> bool:
        if not self.back:
            if self.page.kind == "today":
                return False
            self.forward, self.page = False, Page()
            return True
        self.forward, self.page = False, self.back.pop()
        return True

    def conversation(self, current: str) -> str:
        """The conversation the page shows, given the current one; "" for none."""
        if self.page.kind == "live":
            return current
        return self.page.id if self.page.kind == "conversation" else ""
