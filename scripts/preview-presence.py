#!/usr/bin/env python3
"""Walks the floating Milo (Presence/PresenceWindow.qml) and the "Milo is working" frame through every phase, state
and feeling with a stand-in presence, and saves frames along each change to build/qml-shots/presence/.

    cd brain && uv run --extra desktop python ../scripts/preview-presence.py [--only NAME] [--dark] [--reduced]

Nothing shows on screen: the windows are shown far off every screen and grabbed through the GPU (the
"offscreen" platform draws with Qt's software renderer, which has no shapes or effects). Exits 1 if Qt warned about anything.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "brain" / "src"))

from PySide6.QtCore import QByteArray, QPointF, QUrl, qInstallMessageHandler  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401  (so QML windows come back as QQuickWindow)

OUT = ROOT / "build" / "qml-shots" / "presence"
WARNINGS: list[str] = []

SPEECH = ["Sure, I'll put it in your calendar.",
          "Sure, I'll put it in your calendar. Friday at ten, with Anna, in the small room."]

# Each scene: a name, then steps of (seconds to hold, changes to the presence, frame times in ms to grab).
SCENES = [
    ("idle", [(1.2, {}, [1100])]),
    ("dictate", [
        (0.4, {"phase": "armed", "mode": "dictate"}, [0, 40, 120, 350]),
        (1.4, {"phase": "listening", "state": "dictating", "partial": "Thanks for the"}, [60, 200, 600, 1300]),
        (0.6, {"partial": "Thanks for the notes, I'll send the figures by Friday"}, [300]),
        (0.5, {"phase": "caught", "state": "transcribing"}, [0, 80, 200, 450]),
        (0.8, {"phase": "pasted", "state": "idle", "partial": ""}, [60, 300, 700]),
        (0.6, {"phase": ""}, [0, 60, 130, 500]),
    ]),
    ("talk", [
        (0.3, {"phase": "armed", "mode": "talk"}, [100]),
        (1.0, {"phase": "listening", "state": "listening", "handsFree": True, "partial": ""}, [150, 900]),
        (0.8, {"partial": "When is my next meeting with Anna?"}, [700]),
        (0.5, {"phase": "caught"}, [400]),
        (0.8, {"phase": "transcribing", "state": "transcribing", "handsFree": False}, [300, 700]),
        (1.4, {"phase": "thinking", "state": "thinking", "partial": "",
               "heard": "When is my next meeting with Anna?"}, [100, 600, 1300]),
        (1.6, {"phase": "", "state": "speaking", "speaking": True, "bubble": SPEECH[0]}, [0, 120, 400, 900, 1500]),
        (1.6, {"bubble": SPEECH[1], "emotion": "happy"}, [100, 700, 1500]),
        (1.0, {"state": "idle", "speaking": False, "level": 0}, [200, 900]),
        (0.8, {"bubble": "", "heard": "", "emotion": "neutral"}, [0, 120, 700]),
    ]),
    ("question", [
        (1.0, {"state": "idle", "bubble": "", "question": {"question": "Send the email to Anna now?", "money": False,
                                                            "always": False, "choices": []}}, [80, 900]),
        (1.0, {"question": {"question": "Pay €24.90 for the train ticket to Berlin?", "money": True, "always": False,
                            "choices": []}}, [900]),
        (1.0, {"question": {"question": "Work in Excel to fill in the table?", "money": False, "always": True,
                            "choices": []}}, [900]),
        (0.6, {"question": {}}, [500]),
    ]),
    ("feelings", [(1.3, {"emotion": e}, [60, 300, 1200])
                  for e in ("excited", "concerned", "sad", "confused", "thinking", "neutral")]),
    ("sleepy", [
        (1.5, {"drowsy": True}, [200, 1400]),
        (1.0, {"drowsy": False}, [300, 900]),
    ]),
    ("meeting", [
        (1.2, {"meeting": {"phase": "recording", "elapsed": 754, "step": "", "error": ""}}, [60, 300, 1100]),
        (0.8, {"meeting": {"phase": "paused", "elapsed": 760, "step": "", "error": ""}}, [600]),
        (0.8, {"meeting": {"phase": "recording", "elapsed": 761, "step": "",
                           "error": "I can't hear the other side"}}, [600]),
        (1.2, {"meeting": {"phase": "writing", "elapsed": 770, "step": "Finding the decisions", "error": ""}},
         [100, 1100]),
        (0.8, {"meeting": None}, [600]),
    ]),
    ("working", [
        (1.0, {"state": "thinking", "looking": True, "helpersActive": True}, [200, 900]),
        (1.0, {"state": "speaking", "speaking": True, "bubble": "I moved the meeting to Friday.",
               "bubbleAction": {"title": "Undo", "icon": "arrow.uturn.backward", "hint": "Puts it back"}}, [900]),
        (0.8, {"state": "idle", "speaking": False, "looking": False, "helpersActive": False, "bubble": "",
               "bubbleAction": {}}, [700]),
    ]),
    ("offline", [
        (1.0, {"connected": False, "phase": "offline"}, [100, 900]),
        (0.8, {"connected": True, "phase": ""}, [700]),
    ]),
    ("hint", [(1.0, {"hint": "Hold fn and speak to dictate."}, [900]), (0.5, {"hint": ""}, [400])]),
    ("leave", [
        (1.2, {"shown": False}, [0, 150, 350, 600, 1100]),
        (1.0, {"shown": True}, [0, 200, 450, 900]),
    ]),
]

WORKING = [
    (0.8, {"active": True, "step": "Opening Safari", "point": QPointF(700, 400)}, [0, 100, 250, 700]),
    (0.8, {"step": "Clicking “New tab”", "point": QPointF(300, 120), "gesture": "click", "clicks": 1},
     [0, 120, 300, 700]),
    (0.8, {"step": "Typing “youtube.com”", "gesture": "typing"}, [400]),
    (0.6, {"active": False, "step": ""}, [100, 500]),
]


def trap(mode, context, message):
    if "Failed to create depth/stencil buffer" in message:
        return  # Qt's offscreen readback of a never-shown window; harmless
    WARNINGS.append(message)
    print("QT:", message, file=sys.stderr)


def pump(app, seconds, window=None):
    """Runs Qt for `seconds`. An off-screen window isn't exposed, so it lays out and renders only when grabbed: grab
    it every 50 ms, as a screen would refresh it, so layout follows the springs as it does on screen."""
    end = time.monotonic() + seconds
    last = 0.0
    while time.monotonic() < end:
        app.processEvents()
        if window is not None and time.monotonic() - last > 0.05:
            window.grabWindow()
            last = time.monotonic()
        time.sleep(0.004)


def show(window):
    """Shown far off every screen: a hidden window misses some updates (effects, late shapes) in its grabs. Both
    windows are tool windows that never take focus, so nothing moves on the user's desktop."""
    window.setProperty("x", -6000)
    window.setProperty("y", -6000)
    window.setProperty("visible", True)


def save(window, path: Path):
    # A hidden window lays out (polishes) only when it renders: one grab to lay out, a moment, the real one.
    window.grabWindow()
    QGuiApplication.processEvents()
    window.grabWindow().save(str(path))


def run(app, target, window, steps, prefix):
    index = 0
    for hold, changes, grabs in steps:
        for key, value in changes.items():
            target.setProperty(key, value)
        started = time.monotonic()
        for at in sorted(grabs):
            pump(app, max(0.0, started + at / 1000 - time.monotonic()), window)
            index += 1
            save(window, OUT / f"{prefix}-{index:02d}-{int(at):04d}ms.png")
        pump(app, max(0.0, started + hold - time.monotonic()), window)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="one scene by name, or 'working'")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--reduced", action="store_true")
    args = parser.parse_args()
    os.environ["MILO_APPEARANCE"] = "dark" if args.dark else "light"
    if args.reduced:
        os.environ["MILO_REDUCED_MOTION"] = "1"
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ.pop("QT_QPA_PLATFORM")  # see the docstring

    qInstallMessageHandler(trap)
    app = QGuiApplication(sys.argv)
    from milo.desktop import design
    design.register(app)
    engine = QQmlEngine()
    engine.addImportPath(str(design.QML_DIR))
    OUT.mkdir(parents=True, exist_ok=True)
    backdrop = QColor("#2B2F3A" if args.dark else "#DCE3EC")
    suffix = ("-dark" if args.dark else "") + ("-reduced" if args.reduced else "")

    def make(source):
        component = QQmlComponent(engine)
        component.setData(QByteArray(source.encode()), QUrl.fromLocalFile(str(design.QML_DIR / "preview.qml")))
        obj = component.create()
        if obj is None:
            for error in component.errors():
                print(error.toString(), file=sys.stderr)
            raise SystemExit(1)
        return obj, component

    if args.only in (None, "working"):
        working, _w = make("import QtQuick\nQtObject { property bool active: false; property string step;"
                           " property point point; property string gesture: 'none'; property int clicks: 0 }")
        window, _ww = make("import QtQuick\nimport Milo\nWorkingWindow { visible: false; width: 900; height: 560 }")
        window.setProperty("working", working)
        window.setProperty("color", backdrop)
        show(window)
        run(app, working, window, WORKING, "working" + suffix)
        window.setProperty("visible", False)

    presence, _p = make("import Milo\nPreviewPresence {}")
    window, _c = make("import QtQuick\nimport Milo\nPresenceWindow { visible: false }")
    window.setProperty("presence", presence)
    # A readback of a transparent window loses its alpha; on screen the compositor blends it. Grab over a desktop.
    window.setProperty("color", backdrop)
    show(window)
    level_phase = [0.0]

    def level_tick():
        level_phase[0] += 0.05
        talking = presence.property("state") in ("listening", "dictating", "speaking")
        presence.setProperty("level", 0.35 + 0.3 * math.sin(level_phase[0] * 9) if talking else 0.0)

    from PySide6.QtCore import QTimer
    timer = QTimer()
    timer.timeout.connect(level_tick)
    timer.start(33)

    for name, steps in SCENES:
        if args.only and args.only != name:
            continue
        run(app, presence, window, steps, name + suffix)
    print(f"frames in {OUT}")
    if WARNINGS:
        print(f"{len(WARNINGS)} Qt warnings", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
