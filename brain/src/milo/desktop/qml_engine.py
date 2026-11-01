"""The QML engine as every desktop window uses it: Milo's import path, the design tokens, the view models by name,
and every QML warning kept, so a test (and --smoke-test) can fail on one."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow  # noqa: F401  loaded, so windows come back as QQuickWindow

from .design import Design, register

QML = Path(__file__).resolve().parent / "qml"
_design: Design | None = None


def qml_root() -> Path:
    """The qml folder next to this module in a checkout, or the packaged one in a frozen build."""
    frozen = Path(getattr(sys, "_MEIPASS", "")) / "milo" / "desktop" / "qml"
    return QML if QML.is_dir() else frozen


def design(app) -> Design:
    """The one `Design` singleton, registered once per process before any QML that imports MiloDesign compiles."""
    global _design
    if _design is None:
        _design = register(app)
    return _design


class Engine:
    def __init__(self, app, context: dict[str, QObject]):
        self.design = design(app)
        self.qml = QQmlApplicationEngine()
        self.qml.addImportPath(str(qml_root()))
        self.warnings: list[str] = []
        self.qml.warnings.connect(self._warned)
        self.context = dict(context)  # kept alive: QML holds no reference of its own
        for name, value in context.items():
            self.qml.rootContext().setContextProperty(name, value)
        self._objects: list[QObject] = []

    def _warned(self, warnings) -> None:
        for warning in warnings:
            self.warnings.append(warning.toString())

    def load(self, relative: str, properties: dict | None = None) -> QObject | None:
        """Creates the root object of `qml/<relative>`, setting the `properties` it declares before it completes."""
        path = qml_root() / relative
        if not path.is_file():
            return None
        component = QQmlComponent(self.qml, QUrl.fromLocalFile(str(path)))
        if component.isError():
            self.warnings.extend(error.toString() for error in component.errors())
            return None
        made = component.beginCreate(self.qml.rootContext())
        if made is None:
            self.warnings.extend(error.toString() for error in component.errors())
            return None
        for name, value in (properties or {}).items():
            if made.metaObject().indexOfProperty(name) >= 0:
                made.setProperty(name, value)
        component.completeCreate()
        # Ours, not the JavaScript collector's: a window nobody in QML refers to would otherwise be deleted.
        QQmlEngine.setObjectOwnership(made, QQmlEngine.ObjectOwnership.CppOwnership)
        self._objects.append((component, made))
        return made

    def close(self) -> None:
        """Windows first, then the engine, each on the event loop: a window that outlives its engine, or an engine
        deleted under a window still painting, takes the process down."""
        from PySide6.QtCore import QCoreApplication, QEvent
        for _component, made in self._objects:
            made.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self._objects.clear()
        self.qml.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
