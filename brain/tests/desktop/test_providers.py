"""Provider setup changes only explicit choices, atomically, without account probes."""
import json
import subprocess
import tomllib

import pytest

from milo.adapters.platform import WINDOWS
from milo.config_file import TomlConfigFile
from milo.core.registry import ConfigError
from milo.desktop.providers import CliStatus, ProviderSelection, ProviderSetup, detect_cli

CONFIG = '# My own settings\n[chat]\nuse = "none" # talking choice\n[harness]\nuse = "none" # helper choice\n[ui]\nvoice = false # keep this\n'


def setup(tmp_path, text=CONFIG, *, installed=False):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    file = TomlConfigFile(path, WINDOWS)
    backend = ProviderSetup(file, detector=lambda *_: CliStatus(installed))
    return path, backend


def test_opening_setup_and_detecting_missing_commands_never_changes_config(tmp_path):
    path, backend = setup(tmp_path, CONFIG.replace('use = "none" # talking', 'use = "claude_live" # talking'))
    before = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    assert backend.needs_setup and not backend.clis["chat_claude"].available
    backend.reload()
    assert path.read_bytes() == before and path.stat().st_mtime_ns == stamp


def test_explicit_dictation_only_and_no_helpers_save_without_cli_accounts(tmp_path):
    path, backend = setup(tmp_path)
    assert not backend.needs_setup
    backend.save(ProviderSelection(chat="none", helper="none"))
    result = tomllib.loads(path.read_text(encoding="utf-8"))
    assert result["chat"]["use"] == result["harness"]["use"] == "none"
    assert "# My own settings" in path.read_text(encoding="utf-8")
    assert 'voice = false # keep this' in path.read_text(encoding="utf-8")


def test_api_setup_uses_nested_tables_and_file_reference_only(tmp_path):
    path, backend = setup(tmp_path)
    backend.save(ProviderSelection("openai_compat", "none", "http://localhost:1234/v1", "local-model", "provider.key"))
    result = tomllib.loads(path.read_text(encoding="utf-8"))
    assert result["chat"]["use"] == "openai_compat"
    assert result["chat"]["openai_compat"] == {"base_url": "http://localhost:1234/v1", "model": "local-model", "key_ref": "provider.key"}
    assert "chat.openai_compat" not in result
    assert "# talking choice" in path.read_text(encoding="utf-8")
    assert result["ui"]["voice"] is False


@pytest.mark.parametrize("endpoint,model,key", [
    ("file:///tmp/api", "model", ""), ("https://user:password@example.com/v1", "model", ""),
    ("https://example.com/v1?key=not-for-this-field", "model", ""),
    ("http://localhost:1234/v1", "", ""), ("http://localhost:1234/v1", "model", "../key"),
])
def test_invalid_api_settings_do_not_partially_change_the_file(tmp_path, endpoint, model, key):
    path, backend = setup(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ConfigError):
        backend.save(ProviderSelection("openai_compat", "none", endpoint, model, key))
    assert path.read_bytes() == before


def test_atomic_toml_updates_validate_all_changes_before_replacing(tmp_path):
    path, backend = setup(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ConfigError):
        backend.file.write_many([("chat", "use", "openai_compat"), ("ui", "invented_setting", True)])
    assert path.read_bytes() == before


def test_cli_detection_reads_paths_without_starting_auth_or_other_commands(tmp_path, monkeypatch):
    executable = tmp_path / "claude.exe"
    executable.write_text("not actually executed", encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Setup must not execute account or authentication commands")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    status = detect_cli("claude", str(executable), "chat.claude_live")
    assert status.available and status.path == str(executable)


def test_invalid_existing_config_is_never_overwritten_by_setup(tmp_path):
    path, backend = setup(tmp_path, '[chat\nuse = "claude_live"')
    before = path.read_bytes()
    assert backend.needs_setup and backend.error
    with pytest.raises(ConfigError):
        backend.save(ProviderSelection("none", "none"))
    assert path.read_bytes() == before


def test_codex_can_handle_talking_and_helpers_without_claude(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(CONFIG, encoding="utf-8")
    calls = []
    def detector(name, configured, section):
        calls.append((name, section))
        return CliStatus(name == "codex")
    backend = ProviderSetup(TomlConfigFile(path, WINDOWS), detector=detector)
    backend.save(ProviderSelection(chat="codex_live", helper="codex"))
    assert ("codex", "chat.codex_live") in calls
    saved = tomllib.loads(path.read_text(encoding="utf-8"))
    assert saved["chat"]["use"] == "codex_live" and saved["harness"]["use"] == "codex"
    assert saved["ui"]["voice"] is False


def test_missing_codex_talker_is_explicit_and_does_not_change_config(tmp_path):
    path, backend = setup(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ConfigError, match="codex login"):
        backend.save(ProviderSelection(chat="codex_live", helper="none"))
    assert path.read_bytes() == before
