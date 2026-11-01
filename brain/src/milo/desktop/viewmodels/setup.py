"""The setup page's one way into Python: providers.ProviderSetup for QML, as the QObject `setupBackend`.

Every rule lives in providers.py; this only converts between QML maps and ProviderSelection. It never runs a CLI or
reads an account: the user signs in in their own terminal. An API key the user pastes for an OpenAI-style API comes
in the choice map as "key", goes to providers.py's save() (which writes it alone into ~/Milo/secrets) or into one
request, and is never kept, logged or handed back to QML.

Looking for local servers, listing models and the Test reply run on worker threads (model_probe.py, short timeouts);
their results come back to the UI thread through a queued signal, the newest request winning.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtQml import QJSEngine
from PySide6.QtGui import QDesktopServices

from milo.config_file import TomlConfigFile
from milo.core.registry import ConfigError

from milo.adapters.harness import openai_presets

from .. import model_probe
from ..providers import ProviderSelection, ProviderSetup


def _selection(choice: dict) -> ProviderSelection:
    """A QML map {chat, helper, endpoint, model, keyRef} as the selection providers.py checks and saves."""
    current = ProviderSelection()
    return ProviderSelection(str(choice.get("chat", current.chat)), str(choice.get("helper", current.helper)),
                             str(choice.get("endpoint", "")), str(choice.get("model", "")),
                             str(choice.get("keyRef", "")).strip())


class SetupBackend(QObject):
    """Read on open, checked on every change, written only by save().

    Give it a parent that outlives every page showing it (the application or the main window) and keep it for the
    app's life: QML holds it only by pointer, so it must neither be collected by Python under a live page nor
    deleted by QML's garbage collector."""
    changed = Signal()
    saved = Signal()
    probed = Signal()
    """detected, models or testResult changed."""
    _finished = Signal(str, int, object)  # what, which request, result: from a worker, queued to this thread

    def __init__(self, home: Path, parent=None, *, setup: ProviderSetup | None = None, probe=model_probe):
        """`probe`: model_probe, or a stand-in with its detect/list_models/try_reply for previews."""
        super().__init__(parent)
        QJSEngine.setObjectOwnership(self, QJSEngine.ObjectOwnership.CppOwnership)
        self._home = Path(home)
        if setup is None:
            from milo.adapters.platform import current
            setup = ProviderSetup(TomlConfigFile(self._home / "config.toml", current()))
        self._setup = setup
        self._last_error = ""
        self._probe = probe
        self._detected: list[dict] = []
        self._models: dict = {"endpoint": "", "names": [], "error": "", "busy": False}
        self._test: dict = {"busy": False, "ok": False, "ms": 0, "text": ""}
        self._asked = {"detect": 0, "models": 0, "test": 0}
        self._finished.connect(self._deliver)

    @Property("QVariantMap", notify=changed)
    def selection(self) -> dict:
        s = self._setup.selection
        return {"chat": s.chat, "helper": s.helper, "endpoint": s.endpoint, "model": s.model, "keyRef": s.key_ref}

    @Property("QVariantMap", notify=changed)
    def clis(self) -> dict:
        """chat_claude, chat_codex, helper_codex, helper_claude: {available, detail}."""
        return {key: {"available": status.available, "detail": status.detail}
                for key, status in self._setup.clis.items()}

    @Property(str, notify=changed)
    def configError(self) -> str:
        return self._setup.error

    @Property(bool, notify=changed)
    def needsSetup(self) -> bool:
        return self._setup.needs_setup

    @Property(str, notify=changed)
    def lastError(self) -> str:
        return self._last_error

    @Slot()
    def reload(self) -> None:
        """Looks for the CLIs again; the page keeps what the user typed."""
        self._setup.reload()
        self.changed.emit()

    @Slot("QVariantMap", result=str)
    def validate(self, choice: dict) -> str:
        try:
            self._setup.validate(_selection(choice), key=str(choice.get("key", "")))
        except ConfigError as error:
            return str(error)
        return ""

    @Slot("QVariantMap", result=bool)
    def save(self, choice: dict) -> bool:
        try:
            self._setup.save(_selection(choice), key=str(choice.get("key", "")))
        except (ConfigError, OSError) as error:
            self._last_error = str(error)
            self.changed.emit()
            return False
        self._last_error = ""
        self.changed.emit()
        self.saved.emit()
        return True

    # ---- OpenAI-style APIs

    @Property("QVariantList", constant=True)
    def presets(self) -> list:
        """openai_presets.PRESETS: [{id, label, base_url, key_ref, local, keys_url, model}]."""
        return openai_presets.as_dicts()

    @Slot(str, result=str)
    def presetFor(self, endpoint: str) -> str:
        return openai_presets.matching(endpoint).id

    @Slot(str, result=bool)
    def keySaved(self, key_ref: str) -> bool:
        """A key is already in ~/Milo/secrets/<key_ref> (its contents are never read here)."""
        try:
            return bool(key_ref.strip()) and self._setup.secret_path(key_ref.strip()).is_file()
        except (OSError, ValueError):
            return False

    @Property("QVariantList", notify=probed)
    def detected(self) -> list:
        """Local servers answering now: [{id, label, baseUrl, models}]."""
        return self._detected

    @Property("QVariantMap", notify=probed)
    def models(self) -> dict:
        """{endpoint, names, error, busy}: the models the server at `endpoint` offers."""
        return self._models

    @Property("QVariantMap", notify=probed)
    def testResult(self) -> dict:
        """{busy, ok, ms, text}: the last Test, in plain words."""
        return self._test

    @Slot()
    def detect(self) -> None:
        """Looks for Ollama and LM Studio on this computer."""
        self._run("detect", self._probe.detect)

    @Slot("QVariantMap")
    def fetchModels(self, choice: dict) -> None:
        endpoint = str(choice.get("endpoint", "")).strip()
        key = self._key(choice)
        self._models = {"endpoint": endpoint, "names": self._models["names"] if self._models["endpoint"] == endpoint
                        else [], "error": "", "busy": True}
        self.probed.emit()
        self._run("models", lambda: self._probe.list_models(endpoint, key))

    @Slot("QVariantMap")
    def test(self, choice: dict) -> None:
        """One tiny reply through Milo's own openai_compat adapter, with the key pasted or the one saved."""
        sel, key = _selection(choice), str(choice.get("key", "")).strip()
        key_file = self._setup.secret_path(sel.key_ref) if sel.key_ref and not key else None
        self._test = {"busy": True, "ok": False, "ms": 0, "text": "Asking for a short reply…"}
        self.probed.emit()
        self._run("test", lambda: self._probe.try_reply(sel.endpoint, sel.model, key=key, key_file=key_file))

    def _key(self, choice: dict) -> str:
        """The pasted key, else the saved one, for a request to list models. Never stored."""
        key = str(choice.get("key", "")).strip()
        if key:
            return key
        ref = str(choice.get("keyRef", "")).strip()
        if ref and self.keySaved(ref):
            try:
                from milo.core.secrets import SecretError, read_secret
                return read_secret(self._setup.secret_path(ref), "The API key")
            except SecretError:
                return ""
        return ""

    def _run(self, what: str, work) -> None:
        self._asked[what] += 1
        ticket = self._asked[what]

        def worker():
            try:
                result = work()
            except Exception as error:  # noqa: BLE001 - a probe's failure is shown, never raised into Qt
                result = error
            self._finished.emit(what, ticket, result)

        threading.Thread(target=worker, name=f"setup-{what}", daemon=True).start()

    @Slot(str, int, object)
    def _deliver(self, what: str, ticket: int, result) -> None:
        if ticket != self._asked[what]:
            return  # an older request: the newer one decides
        failed = isinstance(result, Exception)
        if what == "detect":
            self._detected = [] if failed else list(result)
        elif what == "models":
            self._models = {"endpoint": self._models["endpoint"], "names": [] if failed else list(result),
                            "error": str(result) if failed else "", "busy": False}
        else:
            self._test = {"busy": False, "ok": False, "ms": 0, "text": str(result)} if failed else                 {"busy": False, **result}
        self.probed.emit()

    @Slot()
    def openSecrets(self) -> None:
        folder = self._home / "secrets"
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
