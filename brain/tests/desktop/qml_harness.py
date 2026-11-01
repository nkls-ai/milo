"""Loads Milo's QML in a test: the `Milo` module and the `MiloDesign` singleton, with every Qt warning collected.

Runs as a script too, for checks that must not take pytest down if Qt crashes:

    python qml_harness.py churn <QML source file> <times>
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QJSEngine, QQmlComponent, QQmlEngine

from milo.desktop import design

QML = design.QML_DIR / "Milo"
_messages: list[str] = []
# The offscreen platform's own complaints about the machine, not about Milo's QML.
_NOT_OURS = ("QFontDatabase: Cannot find font directory", "Failed to create depth/stencil buffer")
_design = None
_alive: list = []


def messages() -> list[str]:
    return _messages


def setup() -> None:
    """Once per process: the message trap and the Design singleton."""
    global _design
    if _design is not None:
        return
    qInstallMessageHandler(lambda mode, context, text: None if text.startswith(_NOT_OURS) else _messages.append(text))
    app = QGuiApplication.instance()
    _design = design.register(app)


def engine() -> QQmlEngine:
    setup()
    e = QQmlEngine()
    e.addImportPath(str(design.QML_DIR))
    return e


def create(e: QQmlEngine, source: str, url: str = "inline.qml"):
    """An object from QML source; raises with Qt's errors if it doesn't load."""
    component = QQmlComponent(e)
    component.setData(QByteArray(source.encode()), QUrl.fromLocalFile(str(QML / "Presence" / url)))
    obj = component.create()
    if obj is None:
        raise AssertionError("\n".join(err.toString() for err in component.errors()))
    # Kept for the whole run: objects that bind to each other (a window and its presence) must not be deleted one
    # before the other while Qt still evaluates their bindings.
    _alive.append((e, component, obj))
    return obj


def module(path: str):
    """A JS module from qml/Milo, e.g. module("Motion/spring.mjs"), with its engine."""
    e = QJSEngine()
    m = e.importModule(str(QML / path))
    assert not m.isError(), m.toString()
    return e, m


def _churn(source_file: str, times: int) -> None:
    app = QGuiApplication([])
    e = engine()
    source = Path(source_file).read_text(encoding="utf-8")
    for _ in range(times):
        obj = create(e, source)
        app.processEvents()
        obj.deleteLater()
        app.processEvents()
        e.collectGarbage()
        e.clearComponentCache()
    del e
    print("ok")


if __name__ == "__main__":
    if sys.argv[1] == "churn":
        _churn(sys.argv[2], int(sys.argv[3]))
