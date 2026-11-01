"""Load one QML control or page offscreen with plain data, catch its commands and QML warnings, and grab it.

Shared by scripts/preview-pages.py and brain/tests/desktop/test_qml_pages.py, so the screenshots and the tests load
pages exactly the same way. Pages are dumb: their inputs are wire-shaped data, their output `command` messages.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickView

from . import design

PAGES = design.QML_DIR / "Milo" / "Pages"
CONTROLS = design.QML_DIR / "Milo" / "Controls"
SAMPLES = Path(__file__).resolve().parents[3] / "tests" / "desktop" / "page_samples"
_NOISE = ("QFontDatabase: Cannot find font directory", "Note that Qt no longer ships fonts")
_WINDOWS_FONTS = ("SegUIVar.ttf", "segoeui.ttf", "seguisb.ttf", "segoeuib.ttf")


class Warnings:
    """Every QML warning while installed; tests fail on any."""

    def __init__(self):
        self.messages: list[str] = []
        self._previous = None

    def __enter__(self):
        def handler(kind, context, message):
            # The offscreen platform's note that Qt ships no fonts is about the test machine, not the page.
            if kind not in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg) and not message.startswith(_NOISE):
                where = f"{context.file}:{context.line}: " if context.file else ""
                self.messages.append(where + message)
        self._previous = qInstallMessageHandler(handler)
        return self

    def __exit__(self, *exc):
        qInstallMessageHandler(self._previous)


_design: design.Design | None = None
_engine: QQmlEngine | None = None


def application() -> QGuiApplication:
    """The process's application with Milo's design registered, and Windows' fonts on the offscreen platform, which
    otherwise has none and draws boxes."""
    global _design, _engine
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    if _design is None:
        if sys.platform == "win32" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            for name in _WINDOWS_FONTS:
                QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name))
            # The offscreen font database knows the variable font only by its family, not its named instances.
            QFont.insertSubstitution("Segoe UI Variable Text", "Segoe UI")
            QFont.insertSubstitution("Segoe UI Variable Display", "Segoe UI Variable")
        _design = design.register(app)
        # One engine for every view: the Design singleton instance belongs to the first engine that reads it.
        _engine = QQmlEngine()
        _engine.addImportPath(str(design.QML_DIR))
    return app


def set_appearance(appearance: str | None) -> None:
    """"light" or "dark" for everything loaded from now on and everything showing; None gives the system's back,
    so nothing of a preview stays in the environment of what runs after it."""
    if appearance is None:
        os.environ.pop("MILO_APPEARANCE", None)
    else:
        os.environ["MILO_APPEARANCE"] = appearance
    if _design is not None:
        _design.changed.emit()


@dataclass
class Loaded:
    view: QQuickView
    root: QQuickItem
    commands: list[dict] = field(default_factory=list)
    actions: list[tuple[str, object]] = field(default_factory=list)
    keep: list = field(default_factory=list)
    """Python objects the page holds (a SetupBackend): alive until the view is gone."""

    def find(self, path: str) -> QQuickItem:
        """The item with objectName `path`, or "row/button" for the button named so inside the row named so; pages
        name the controls tests click."""
        item = self.root
        for name in path.split("/"):
            item = _named(item, name)
            if item is None:
                raise LookupError(f"No item named {path!r}")
        return item

    def click(self, name: str) -> None:
        """Clicks a button the way a user's click ends: its clicked() signal."""
        item = self.find(name)
        if not item.isVisible() or not item.isEnabled():
            raise AssertionError(f"{name!r} can't be clicked: hidden or disabled")
        item.clicked.emit()
        settle()

    def set(self, **props) -> None:
        for key, value in props.items():
            self.root.setProperty(key, value)
        settle()

    def grab(self, path: Path) -> Path:
        settle(400)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.view.grabWindow().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        return path

    def close(self) -> None:
        """Gone now, not at some later event loop: a view left to a deferred delete outlives the Python objects its
        page holds (a backend, the command lambdas) and crashes whichever test happens to flush it."""
        root = self.view.rootObject()
        for name in ("command", "action"):
            if root is not None and root.metaObject().indexOfSignal(f"{name}(QVariant)" if name == "command"
                                                                    else "action(QString,QVariant)") >= 0:
                getattr(root, name).disconnect()
        self.view.close()
        self.view.setSource(QUrl())
        self.view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QCoreApplication.processEvents()


def _named(parent, name: str):
    """The first item named `name` under `parent`, through the visual tree, where Repeater's rows live."""
    for child in parent.childItems():
        if child.objectName() == name:
            return child
    for child in parent.childItems():
        found = _named(child, name)
        if found is not None:
            return found
    return None


def run_steps(loaded: "Loaded", steps: list) -> None:
    """A sample's interaction: {"click": path}, {"set": [path, property, value]} as typing would, or {"wait": ms}
    for a worker thread's answer."""
    for step in steps:
        if "click" in step:
            loaded.click(step["click"])
        elif "wait" in step:
            settle(step["wait"])
        else:
            path, prop, value = step["set"]
            loaded.find(path).setProperty(prop, value)
            settle()


def settle(ms: int = 30) -> None:
    from PySide6.QtTest import QTest
    QTest.qWait(ms)


def load(path: Path, props: dict | None = None, *, size=(720, 820)) -> Loaded:
    """Shows the QML file at `path` with `props` as its initial properties, on Milo's paper."""
    application()
    view = QQuickView(_engine, None)
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    tokens = design.load_tokens()["colors"]["tint"]
    view.setColor(QColor(tokens[1 if os.environ.get("MILO_APPEARANCE") == "dark" else 0]))
    view.setInitialProperties(props or {})
    view.resize(*size)
    view.setSource(QUrl.fromLocalFile(str(path)))
    if view.status() != QQuickView.Status.Ready:
        raise RuntimeError("\n".join(e.toString() for e in view.errors()))
    view.show()
    root = view.rootObject()
    loaded = Loaded(view, root)
    if root.metaObject().indexOfSignal("command(QVariant)") >= 0:
        root.command.connect(lambda message: loaded.commands.append(_plain(message)))
    if root.metaObject().indexOfSignal("action(QString,QVariant)") >= 0:
        root.action.connect(lambda name, value: loaded.actions.append((name, _plain(value))))
    settle(60)
    return loaded


def _plain(value):
    """A QJSValue or QVariant from QML as plain Python data."""
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return json.loads(json.dumps(value, default=str))


def samples() -> dict[str, dict]:
    """page_samples/<Name>.json by name:
    {"page": "TodayPage" | "file": "qml/X.qml", "size": [w, h], "states": {state: props},
     "interactions": [{"state": state, "steps": [...], "expect": [commands], "actions": [[name, value]]}]}"""
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(SAMPLES.glob("*.json"))}


def sample_path(sample: dict) -> Path:
    return PAGES / f"{sample['page']}.qml" if "page" in sample else SAMPLES.parent / sample["file"]


def load_sample(sample: dict, state: str) -> Loaded:
    """A sample state's props; a "setupBackend" spec in them becomes a real SetupBackend (see preview_backend)."""
    props = dict(sample["states"][state])
    backend = preview_backend(props.pop("setupBackend")) if isinstance(props.get("setupBackend"), dict) else None
    if backend is not None:
        props["setupBackend"] = backend
    loaded = load(sample_path(sample), props, size=tuple(sample.get("size", (720, 820))))
    loaded.keep.append(backend)
    settle(120)  # the backend's first look for local servers comes back from its thread
    return loaded


class _CannedProbe:
    """model_probe's answers from a sample, so previews show each state without a network."""

    def __init__(self, spec: dict):
        self.spec = spec

    def detect(self):
        return self.spec.get("detected", [])

    def list_models(self, endpoint, key=""):
        from .model_probe import ProbeError
        found = self.spec.get("models", {}).get(endpoint.strip().rstrip("/"), "Nothing answered there.")
        if isinstance(found, str):
            raise ProbeError(found)
        return found

    def try_reply(self, *args, **kwargs):
        return self.spec.get("test", {"ok": True, "ms": 420, "reply": "OK", "text": "Answered in 420 ms: “OK”"})


def preview_backend(spec: dict):
    """A SetupBackend over a throwaway Milo folder: {"config": toml, "installed": [cli names], "secrets": [file
    names], and _CannedProbe's "detected", "models" (endpoint: names or an error), "test"}."""
    import tempfile
    from milo.adapters.platform import current
    from milo.config_file import TomlConfigFile
    from .providers import CliStatus, ProviderSetup
    from .viewmodels.setup import SetupBackend
    home = Path(tempfile.mkdtemp(prefix="milo-preview-"))
    (home / "config.toml").write_text(spec.get("config", ""), encoding="utf-8")
    for name in spec.get("secrets", []):
        (home / "secrets").mkdir(exist_ok=True)
        (home / "secrets" / name).write_text("sk-preview\n", encoding="utf-8")
    installed = set(spec.get("installed", []))
    detector = lambda name, *_: CliStatus(name in installed, detail="Installed" if name in installed else "Not found")
    return SetupBackend(home, setup=ProviderSetup(TomlConfigFile(home / "config.toml", current()), detector=detector),
                        probe=_CannedProbe(spec))


def wire_shapes() -> dict[str, set[str]]:
    """Every app_to_brain type in protocol/messages.json and the keys its examples use."""
    protocol = json.loads((design.tokens_path().parent / "messages.json").read_text(encoding="utf-8"))
    shapes: dict[str, set[str]] = {}
    for example in protocol["app_to_brain"]:
        shapes.setdefault(example["type"], set()).update(example)
    return shapes


def wire_problems(command: dict, shapes: dict[str, set[str]] | None = None) -> list[str]:
    """Why `command` isn't a message protocol/messages.json knows, or nothing."""
    shapes = shapes or wire_shapes()
    kind = command.get("type")
    if kind not in shapes:
        return [f"unknown command type {kind!r}"]
    extra = set(command) - shapes[kind]
    return [f"{kind}: key {key!r} isn't in protocol/messages.json" for key in sorted(extra)]
