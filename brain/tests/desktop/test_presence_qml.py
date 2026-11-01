"""Presence/: the floating Milo and the working frame load, walk every phase without a QML warning, and say what
the Mac says."""
from __future__ import annotations

import json
import time

import pytest

pytest.importorskip("PySide6.QtQuick")

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QJSEngine  # noqa: E402

from milo.desktop.presentation import voice_phase  # noqa: E402

from . import qml_harness as harness  # noqa: E402

PHASES = ["", "armed", "listening", "caught", "transcribing", "pasted", "thinking", "offline"]


def pump(seconds):
    app = QGuiApplication.instance()
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def test_capsule_words_match_the_shell():
    """voice.mjs and presentation/voice_phase.py say the same for every phase, mode and words."""
    e = QJSEngine()
    voice = e.importModule(str(harness.QML / "Presence" / "voice.mjs"))
    e.globalObject().setProperty("Voice", voice)
    for phase in PHASES:
        for mode in ("talk", "dictate"):
            for words in (False, True):
                ours = e.evaluate(f"Voice.label({json.dumps(phase)}, {json.dumps(mode)}, {json.dumps(words)})")
                theirs = voice_phase.label(voice_phase.VoicePhase(phase, mode) if phase else None, words=words)
                assert ours.toString() == theirs, (phase, mode, words)
    for seconds in (1, 10, 30):
        assert e.evaluate(f"Voice.thinkingLabel({seconds}, false)").toString() == \
            voice_phase.thinking_label(seconds, words=False)
    long = "word " * 60
    assert e.evaluate(f"Voice.tail({json.dumps(long)})").toString() == voice_phase.tail(long)
    for level in (0, 0.03, 0.2, 0.5, 1):
        assert e.evaluate(f"Voice.levelHeight({level})").toNumber() == pytest.approx(voice_phase.level_height(level))


def test_presence_window_walks_every_phase_without_warnings():
    e = harness.engine()
    before = len(harness.messages())
    presence = harness.create(e, "import Milo\nPreviewPresence {}")
    window = harness.create(e, "import QtQuick\nimport Milo\nPresenceWindow { visible: false }")
    window.setProperty("presence", presence)
    pump(0.2)
    for phase in PHASES:
        presence.setProperty("phase", phase)
        presence.setProperty("mode", "dictate")
        presence.setProperty("partial", "Thanks for the notes" if phase in ("listening", "caught") else "")
        pump(0.08)
    presence.setProperty("state", "speaking")
    presence.setProperty("bubble", "Sure, I'll put it in your calendar.")
    presence.setProperty("reveal", {"shown": 5, "fresh": 4, "alpha": 0.5})
    presence.setProperty("canStop", True)
    pump(0.2)
    presence.setProperty("question", {"id": "q1", "question": "Send it?", "money": True, "always": False,
                                      "choices": []})
    presence.setProperty("meeting", {"phase": "recording", "elapsed": 61, "step": "", "error": ""})
    presence.setProperty("emotion", "excited")
    pump(0.2)
    presence.setProperty("question", {})
    presence.setProperty("meeting", None)
    presence.setProperty("shown", False)
    pump(0.3)
    presence.setProperty("shown", True)
    pump(0.2)
    assert harness.messages()[before:] == []
    assert window.property("inputRegion")  # Milo's square at least takes clicks


def test_working_window_glides_without_warnings():
    e = harness.engine()
    before = len(harness.messages())
    working = harness.create(e, "import QtQuick\nQtObject { property bool active: false; property string step;"
                                " property point point; property string gesture: 'none'; property int clicks: 0 }")
    window = harness.create(e, "import QtQuick\nimport Milo\nWorkingWindow { visible: false; width: 800; height: 500 }")
    window.setProperty("working", working)
    working.setProperty("active", True)
    working.setProperty("step", "Opening Safari")
    working.setProperty("point", QPointF(300, 200))
    pump(0.3)
    working.setProperty("gesture", "click")
    working.setProperty("clicks", 1)
    working.setProperty("point", QPointF(500, 100))
    pump(0.3)
    working.setProperty("active", False)
    pump(0.3)
    assert harness.messages()[before:] == []
