"""The QML desktop's composition root: the application, the engine and its windows, the brain connection, the
platform, the controller, the tray. main.py parses the arguments and calls `run` or `smoke`."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication

from .controller import DesktopController, ViewModels
from .overlay import OverlayTracker
from .qml_engine import Engine
from .tray import Tray, icon
from .viewmodels.pages import PageCatalog

MAIN = "Milo/Window/MainWindow.qml"
PRESENCE = "Milo/Presence/PresenceWindow.qml"
WORKING = "Milo/Presence/WorkingWindow.qml"


def application() -> QApplication:
    """A QApplication, not a QGuiApplication: the tray icon and its menu are still widgets."""
    app = QApplication.instance() or QApplication(sys.argv[:1])
    # Qt's offscreen plugin on Windows doesn't list the system's fonts; load Segoe UI so renders are meaningful.
    if not QFontDatabase.families():
        root = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("segoeui.ttf", "segoeuib.ttf", "segoeuisl.ttf", "seguisb.ttf", "SegUIVar.ttf"):
            if (root / name).is_file():
                QFontDatabase.addApplicationFont(str(root / name))
        if "Segoe UI" in QFontDatabase.families():
            app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("Milo")
    app.setOrganizationName("Milo")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icon())
    return app


class Shell:
    """The windows QML draws, made from one engine bound to one set of view models."""

    def __init__(self, app, views: ViewModels, *, setup_backend=None, overlays: bool = True):
        self.views = views
        self.pages = PageCatalog()
        self.engine = Engine(app, {**views.context(), "shell": views.window, "pages": self.pages,
                                   "setupBackend": setup_backend})
        self.window = self.engine.load(MAIN)
        overlay = {"presence": views.presence, "working": views.working}
        self.presence = self.engine.load(PRESENCE, overlay) if overlays else None
        self.working = self.engine.load(WORKING, overlay) if overlays else None
        # Click-through outside Milo and his surfaces, and the pointer for his eyes.
        self.tracker = OverlayTracker(self.presence, views.presence) if self.presence is not None else None
        if self.window is None:
            raise RuntimeError("The Milo window failed to load:\n" + "\n".join(self.engine.warnings))

    def show_window(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.requestActivate()

    def show_page(self, page: str) -> None:
        self.views.route.go(page)
        self.show_window()

    def close(self) -> None:
        for window in (self.window, self.presence, self.working):
            if window is not None:
                window.close()
        self.engine.close()


def copier(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def reveal(home: Path, path: str) -> None:
    """Shows a file's folder (or a folder) in the file manager; a relative path is in the workspace."""
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    target = Path(path).expanduser()
    target = target if target.is_absolute() else home / target
    if target.suffix == ".md" and target.is_file():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target if target.is_dir() else target.parent)))


def run(home: Path, *, no_brain: bool = False) -> int:
    """The real app: one instance per workspace, a brain launched unless one answers, global keys and the tray."""
    from milo.memory.workspace import Workspace

    from .client import BrainConnection
    from .instance import DesktopInstance
    from .launcher import BrainLauncher
    from .office_client import OfficeClient
    from .platform import create, create_hotkeys

    app = application()
    Workspace(home).ensure()
    instance = DesktopInstance(home)
    if not instance.start():
        return 0
    from .viewmodels.setup import SetupBackend
    views = ViewModels()
    backend = SetupBackend(home, app)  # app-lifetime: QML only holds it by pointer
    shell = Shell(app, views, setup_backend=backend)
    connection = BrainConnection(home / "run" / "brain.sock")
    native = create(home)
    hotkeys = create_hotkeys()
    hotkeys.set_diagnostics_path(home / "logs" / "hotkeys.json")
    office = OfficeClient(home, None)
    controller = DesktopController(home, views, connection, native, hotkeys, office=office, copy=copier)
    controller.window_requested.connect(shell.show_window)
    instance.activation_requested.connect(controller.open_window)
    connection.status.connect(lambda text: None)  # socket errors while reconnecting: the notice says it already

    launcher = None if no_brain else BrainLauncher(home)

    def setup():
        """Connections & models: the Setup page, read afresh."""
        backend.reload()
        shell.show_page("setup")
    views.window.setupRequested.connect(setup)
    views.presence.setupRequested.connect(setup)
    views.window.set(canRestart=launcher is not None)
    if launcher is not None:
        launcher.status.connect(lambda text: views.window.set(notice=text))
        launcher.setup_needed.connect(setup)
        views.window.restartRequested.connect(launcher.restart)
    views.window.quitRequested.connect(app.quit)
    views.window.revealRequested.connect(lambda path: reveal(home, path))
    if launcher is not None:
        backend.saved.connect(launcher.apply_configuration)

    tray = Tray(app, open_window=controller.open_window, setup=setup,
                stop=lambda: controller.send({"type": "stop_all"}),
                restart=launcher.restart if launcher is not None else None, quit_app=app.quit)
    if Tray.available():
        tray.show()
    app.aboutToQuit.connect(controller.close)
    app.aboutToQuit.connect(shell.close)
    app.aboutToQuit.connect(instance.close)
    if launcher is not None:
        app.aboutToQuit.connect(launcher.stop)

    shell.show_window()
    connection.start()
    hotkeys.start()
    if launcher is not None:
        # Without a provider choice there is nothing to start yet: the Setup page comes first.
        QTimer.singleShot(100, lambda: setup() if not connection.connected and backend.needsSetup
                          else launcher.ensure())
    return app.exec()


def smoke(shots: Path, scenes: list[str] | None = None) -> int:
    """Renders the real QML offscreen-safe, with a scripted brain and no devices, hooks or models: plays each scene
    and saves the main window and the overlays after it. Fails on any QML warning."""
    from . import script

    app = application()
    views = ViewModels()
    shell = Shell(app, views)
    recorder = script.Recorder()
    controller = DesktopController(shots, views, recorder, copy=copier)
    shell.window.show()
    for window in (shell.presence, shell.working):
        if window is not None:
            window.show()
    shots.mkdir(parents=True, exist_ok=True)
    order = scenes or ["welcome", "turn", "rest", "dictation", "helpers", "confirm"]
    result = {"code": 0}

    def grab(name: str) -> None:
        try:
            pictures(name)
        except Exception as error:
            print(f"Couldn't grab {name}: {error}", file=sys.stderr)
            result["code"] = 1

    def pictures(name: str) -> None:
        for label, window in (("window", shell.window), ("presence", shell.presence), ("working", shell.working)):
            if window is not None and window.isVisible():
                window.grabWindow().save(str(shots / f"{name}-{label}.png"))

    def next_scene(index: int = 0) -> None:
        if index >= len(order):
            if shell.engine.warnings:
                print("QML warnings:\n" + "\n".join(shell.engine.warnings), file=sys.stderr)
                result["code"] = 1
            elif sys.stdout is not None:
                print(f"Desktop smoke test passed: {shots}")
            app.exit(result["code"])
            return
        name = order[index]

        def settled():
            # Long enough for the springs to come to rest before the picture.
            QTimer.singleShot(900, lambda: (grab(f"{index + 1:02d}-{name}"), next_scene(index + 1)))
        script.play(controller, script.SCENES[name](), settled)

    QTimer.singleShot(300, next_scene)
    code = app.exec()
    shell.close()
    return code or result["code"]
