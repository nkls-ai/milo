"""protocol/design.json for QML: Milo's colours, spacing and springs, plus light/dark and reduced motion."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication

_NAME = "design.json"


def tokens_path() -> Path:
    """The repo's protocol/design.json in a checkout, the packaged copy in a frozen build."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[4] / "protocol" / _NAME,
                      Path(getattr(sys, "_MEIPASS", "")) / "protocol" / _NAME,
                      here.parent / "qml" / "Milo" / _NAME):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(_NAME)


def load_tokens() -> dict:
    return json.loads(tokens_path().read_text(encoding="utf-8"))


class Design(QObject):
    """Registered as the QML singleton `Design`; Milo/Theme.qml is the only reader."""
    changed = Signal()

    def __init__(self, app: QGuiApplication | None = None, parent=None):
        super().__init__(parent)
        self._tokens = load_tokens()
        self._app = app
        if app is not None:
            app.styleHints().colorSchemeChanged.connect(lambda *_: self.changed.emit())

    @Property("QVariantMap", notify=changed)
    def tokens(self):
        return self._tokens

    @Property(bool, notify=changed)
    def dark(self) -> bool:
        requested = os.environ.get("MILO_APPEARANCE", "").lower()
        if requested in ("dark", "light"):
            return requested == "dark"
        app = self._app or QGuiApplication.instance()
        return app is not None and app.styleHints().colorScheme() == Qt.ColorScheme.Dark

    @Property(bool, notify=changed)
    def reducedMotion(self) -> bool:
        return os.environ.get("MILO_REDUCED_MOTION", "") == "1"


QML_DIR = Path(__file__).resolve().parent / "qml"


_registered: Design | None = None


def register(app: QGuiApplication | None = None) -> Design:
    """Makes `import MiloDesign` and `import Milo` work: call before loading QML, and add QML_DIR to the engine's
    import path. Later calls return the first instance: registering the type again breaks every later load."""
    global _registered
    if _registered is not None:
        return _registered
    from PySide6.QtQml import QJSEngine, qmlRegisterSingletonType

    design = _registered = Design(app)
    # One instance for every engine (a registered instance reaches only the first), and ours: closing an engine
    # must not delete it under the next.
    QJSEngine.setObjectOwnership(design, QJSEngine.ObjectOwnership.CppOwnership)
    qmlRegisterSingletonType(Design, "MiloDesign", 1, 0, "Design", lambda engine: design)
    return design
