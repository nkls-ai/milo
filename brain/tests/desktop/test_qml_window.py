"""The real Milo window in QML, offscreen, driven by the scripted brain: it must load and run every scene and page
without a single QML warning. Screenshots go to build/qml-shots/window/ for a look against the Mac's views."""
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QCoreApplication

from milo.desktop import script
from milo.desktop.app import Shell, application
from milo.desktop.controller import DesktopController, ViewModels

SHOTS = Path(__file__).parents[3] / "build" / "qml-shots" / "window"


def settle(seconds=0.8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture(scope="module")
def window(tmp_path_factory):
    # One engine for the module, as in the app: Qt doesn't take engines torn down under live windows well.
    tmp_path = tmp_path_factory.mktemp("qml")
    app = application()
    views = ViewModels()
    shell = Shell(app, views, overlays=False)
    root, engine = shell.window, shell.engine
    connection = script.Recorder()
    controller = DesktopController(tmp_path, views, connection)
    root.show()
    settle(0.3)
    yield root, controller, engine, connection
    controller.close()
    shell.close()
    settle(0.1)


def shoot(root, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    assert root.grabWindow().save(str(SHOTS / f"test-{name}.png"))


def test_every_scene_runs_without_a_warning(window):
    root, controller, engine, _ = window
    engine.warnings.clear()
    for name in ("welcome", "turn", "rest", "dictation", "helpers", "confirm"):
        script.play_now(controller, script.SCENES[name]())
        settle()
        shoot(root, name)
    assert engine.warnings == []


def test_every_page_and_the_narrow_window(window):
    root, controller, engine, connection = window
    engine.warnings.clear()
    script.play_now(controller, script.welcome())
    route = controller.views.route
    for page, page_id in (("today", ""), ("usage", ""), ("knowledge", ""), ("routines", ""), ("settings", ""),
                          ("task", "t1"), ("conversation", "c-smoke-4"), ("conversation", "c-smoke-2"), ("live", "")):
        route.go(page, page_id)
        settle(0.6)
        shoot(root, f"page-{page}-{page_id or 'main'}")
    assert engine.warnings == []
    root.setWidth(520)
    route.setSidebarShown(True)
    settle()
    shoot(root, "narrow")
    assert engine.warnings == []


def test_the_composer_sends_and_clears(window):
    root, controller, engine, connection = window
    engine.warnings.clear()
    script.play_now(controller, script.welcome())
    assert controller.views.window.sendText("hello", "")
    assert connection.commands[-1]["type"] == "text"
    assert engine.warnings == []
