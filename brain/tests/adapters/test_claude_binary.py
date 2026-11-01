"""GUI launches discover Claude Code without depending on inherited PATH."""
from pathlib import Path

import pytest

from milo.adapters.harness import _binary
from milo.core.registry import ConfigError


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.setattr(_binary.sys, "platform", "win32")
    monkeypatch.setattr(_binary.shutil, "which", lambda name: None)
    monkeypatch.setattr(_binary.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData/Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData/Roaming"))
    return tmp_path


def make_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test executable placeholder")
    return path


def find():
    return _binary.find_binary("", "claude", section="chat.claude_live")


def test_finds_winget_link_when_gui_path_omits_it(installation):
    expected = make_file(installation / "AppData/Local/Microsoft/WinGet/Links/claude.exe")
    assert find() == str(expected)
    assert _binary.executable_command(find(), ["--version"]) == [str(expected), "--version"]


def test_finds_winget_package_when_link_is_missing(installation):
    expected = make_file(installation / "AppData/Local/Microsoft/WinGet/Packages" /
                         "Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe/claude.exe")
    assert find() == str(expected)


def test_explicit_path_and_standard_native_install_keep_precedence(installation):
    make_file(installation / "AppData/Local/Microsoft/WinGet/Links/claude.exe")
    expected = make_file(installation / ".local/bin/claude.exe")
    assert find() == str(expected)
    assert _binary.find_binary("my-cli.exe", "claude", section="chat.claude_live") == "my-cli.exe"


def test_claude_desktop_gui_does_not_count_as_code_cli(installation):
    make_file(installation / "AppData/Local/Programs/Claude/claude.exe")
    make_file(installation / "AppData/Local/Microsoft/WinGet/Packages/Anthropic.Claude_1/claude.exe")
    with pytest.raises(ConfigError, match="could not find"):
        find()


def test_directory_named_claude_is_not_a_cli(installation):
    (installation / ".local/bin/claude.exe").mkdir(parents=True)
    with pytest.raises(ConfigError, match="could not find"):
        find()
