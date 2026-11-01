"""SetupBackend hands QML the provider choice from providers.py and writes only what save() is given."""
import tomllib

import pytest

pytest.importorskip("PySide6.QtCore")

from milo.adapters.platform import WINDOWS  # noqa: E402
from milo.config_file import TomlConfigFile  # noqa: E402
from milo.desktop.providers import CliStatus, ProviderSetup  # noqa: E402
from milo.desktop.viewmodels.setup import SetupBackend  # noqa: E402

CONFIG = '# mine\n[chat]\nuse = "claude_live"\n[harness]\nuse = "codex"\n'


def backend(tmp_path, *, installed=("claude",)):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG, encoding="utf-8")
    detector = lambda name, *_: CliStatus(name in installed, detail="found" if name in installed else "missing")
    return path, SetupBackend(tmp_path, setup=ProviderSetup(TomlConfigFile(path, WINDOWS), detector=detector))


def test_reads_the_choice_and_which_clis_are_there(tmp_path):
    _, b = backend(tmp_path)
    assert b.selection == {"chat": "claude_live", "helper": "codex", "endpoint": "", "model": "", "keyRef": ""}
    assert b.clis["chat_claude"] == {"available": True, "detail": "found"}
    assert b.clis["helper_codex"]["available"] is False
    assert b.needsSetup and b.configError == ""


def test_validate_explains_and_never_writes(tmp_path):
    path, b = backend(tmp_path)
    before = path.read_bytes()
    assert "helper CLI wasn't found" in b.validate({"chat": "claude_live", "helper": "codex"})
    assert b.validate({"chat": "claude_live", "helper": "claude"}) == ""
    assert "http://" in b.validate({"chat": "openai_compat", "helper": "none", "endpoint": "nope", "model": "m"})
    assert path.read_bytes() == before


def test_save_writes_the_choice_and_says_so(tmp_path):
    path, b = backend(tmp_path)
    heard = []
    b.saved.connect(lambda: heard.append(True))
    assert b.save({"chat": "openai_compat", "helper": "none", "endpoint": "http://localhost:11434/v1",
                   "model": "llama", "keyRef": " "})
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    assert config["chat"]["use"] == "openai_compat" and config["harness"]["use"] == "none"
    assert config["chat"]["openai_compat"]["model"] == "llama"
    assert heard == [True] and b.lastError == ""


def test_a_refused_save_keeps_the_file_and_reports(tmp_path):
    path, b = backend(tmp_path)
    before = path.read_bytes()
    assert not b.save({"chat": "codex_live", "helper": "none"})
    assert "Codex CLI wasn't found" in b.lastError
    assert path.read_bytes() == before


def test_the_setup_page_saves_through_the_backend(tmp_path):
    """The real page with the real backend: choosing Claude for helpers clears the problem and Save writes it."""
    pytest.importorskip("PySide6.QtQuick")
    from milo.desktop import qml_preview as q
    path, b = backend(tmp_path)
    q.application()
    with q.Warnings() as warnings:
        loaded = q.load(q.PAGES / "SetupPage.qml", {"setupBackend": b}, size=(600, 1300))
        assert loaded.find("problem").isVisible()
        assert not loaded.find("save").isEnabled()
        q.run_steps(loaded, [{"click": "helpers/Claude CLI"}, {"click": "save"}])
        loaded.close()
    assert warnings.messages == []
    assert tomllib.loads(path.read_text(encoding="utf-8"))["harness"]["use"] == "claude"
    assert loaded.actions == [("saved", None)]
