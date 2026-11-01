"""`pages`: where each page's QML lives, so the window hosts only pages that exist and a missing one shows a note
instead of breaking the window. The pages are dumb: they get wire-shaped data and emit wire commands."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot

MILO = Path(__file__).resolve().parents[1] / "qml" / "Milo"
PAGES = MILO / "Pages"
# Milo's own figure for the empty conversation, once Milo/Wren has one that stands alone.
WREN = ("Wren/WrenFigure.qml", "Wren/Figure.qml")
# Route page → the file under qml/Milo/Pages that shows it.
FILES = {
    "today": "TodayPage.qml",
    "usage": "UsagePage.qml",
    "task": "TaskPage.qml",
    "meeting": "MeetingPage.qml",
    "knowledge": "KnowledgePage.qml",
    "routines": "RoutinesPage.qml",
    "helpers": "HelpersPage.qml",
    "settings": "SettingsPage.qml",
    "setup": "SetupPage.qml",
    "confirm": "ConfirmPage.qml",
}


class PageCatalog(QObject):
    def __init__(self, root: Path = PAGES, parent=None):
        super().__init__(parent)
        self.root = root

    @Slot(str, result=str)
    def url(self, page: str) -> str:
        """The page's file URL, or "" while that page isn't written yet."""
        name = FILES.get(page)
        path = self.root / name if name else None
        return QUrl.fromLocalFile(str(path)).toString() if path is not None and path.is_file() else ""

    @Slot(result=str)
    def wren(self) -> str:
        found = next((MILO / name for name in WREN if (MILO / name).is_file()), None)
        return QUrl.fromLocalFile(str(found)).toString() if found else ""
