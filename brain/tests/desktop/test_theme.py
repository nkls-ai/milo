"""Theme.qml: every colour binds to a real colour from design.json, in light and dark."""
from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6.QtQuick")

from PySide6.QtGui import QColor  # noqa: E402

from milo.desktop import design  # noqa: E402

from . import qml_harness as harness  # noqa: E402


def theme_colours(obj) -> dict[str, QColor]:
    meta = obj.metaObject()
    found = {}
    for i in range(meta.propertyOffset(), meta.propertyCount()):
        prop = meta.property(i)
        if prop.typeName() == "QColor":
            found[prop.name()] = obj.property(prop.name())
    return found


@pytest.mark.parametrize("appearance", ["light", "dark"])
def test_every_theme_colour_is_valid(monkeypatch, appearance):
    monkeypatch.setenv("MILO_APPEARANCE", appearance)
    e = harness.engine()
    before = len(harness.messages())
    obj = harness.create(e, "import QtQuick\nimport Milo\nQtObject { property var theme: Theme }")
    theme = obj.property("theme")
    colours = theme_colours(theme)
    # "onPrimary" was read as a signal handler and never bound: an invalid colour, black text on buttons
    assert "primaryInk" in colours and len(colours) > 10
    for name, colour in colours.items():
        assert isinstance(colour, QColor) and colour.isValid(), name
    pair = 1 if appearance == "dark" else 0
    tokens = design.load_tokens()
    for name, values in tokens["colors"].items():
        qml_name = "primaryInk" if name == "onPrimary" else name
        assert colours[qml_name] == QColor(values[pair]), name
    assert harness.messages()[before:] == []


def test_packaged_tokens_match_the_protocol():
    packaged = design.QML_DIR / "Milo" / "design.json"
    assert json.loads(packaged.read_text(encoding="utf-8")) == design.load_tokens()


def test_register_twice_returns_the_same_design_and_theme_still_loads():
    harness.setup()
    first = design.register()
    assert design.register() is first
    e = harness.engine()
    obj = harness.create(e, "import QtQuick\nimport Milo\nQtObject { property color c: Theme.primary }")
    assert obj.property("c").isValid()
