import io

import pytest

from milo import install
from milo.core.registry import TRANSCRIBERS, ConfigError
from milo.memory.workspace import Workspace

LIGHT = '[stt]\nuse = "tones"\n\n[tts]\nuse = "none"\n\n[memory]\nembedder = "hash"\n'
"""Engines that need no model, so `models` runs in a test."""


@pytest.fixture
def home(tmp_path):
    Workspace(tmp_path).ensure()
    return tmp_path


def test_models_gets_hearing_voice_and_memory_ready(home):
    (home / "config.toml").write_text(LIGHT, encoding="utf-8")
    out = io.StringIO()
    assert install.models(home, out) == 0
    lines = out.getvalue().splitlines()
    assert [line.split(" (")[0] for line in lines if "ready in" in line] == ["Hearing", "Voice", "Memory"]
    assert "Hearing (tones)" in out.getvalue() and "Memory (hash)" in out.getvalue()


def test_one_engine_failing_doesnt_stop_the_others(home, monkeypatch):
    (home / "config.toml").write_text(LIGHT, encoding="utf-8")

    def broken(*_):
        raise RuntimeError("no network")

    monkeypatch.setattr(TRANSCRIBERS, "create", broken)
    out = io.StringIO()
    assert install.models(home, out) == 1
    assert "Hearing (tones): failed: no network" in out.getvalue()
    assert "Voice (none): ready" in out.getvalue() and "Memory (hash): ready" in out.getvalue()


def test_configure_sets_chat_and_harness_and_keeps_the_comments(home):
    before = (home / "config.toml").read_text(encoding="utf-8")
    config = install.configure(home, chat="claude_live", harness="claude")
    after = (home / "config.toml").read_text(encoding="utf-8")
    assert config.pluggable("chat")[0] == "claude_live" and config.pluggable("harness")[0] == "claude"
    assert [line for line in before.splitlines() if line.startswith("#")] == \
        [line for line in after.splitlines() if line.startswith("#")]


def test_configure_leaves_what_it_isnt_given(home):
    install.configure(home, harness="claude")
    install.configure(home, chat="none")
    config = install.configure(home)
    assert config.pluggable("harness")[0] == "claude" and config.pluggable("chat")[0] == "none"


def test_codex_only_account_can_be_configured_for_talking_and_helpers(home):
    config = install.configure(home, chat="codex_live", harness="codex")
    assert config.pluggable("chat")[0] == "codex_live"
    assert config.pluggable("harness")[0] == "codex"


def test_an_unknown_name_writes_nothing(home):
    before = (home / "config.toml").read_text(encoding="utf-8")
    with pytest.raises(ConfigError, match="gemini"):
        install.configure(home, chat="gemini")
    with pytest.raises(ConfigError, match="cursor"):
        install.configure(home, chat="none", harness="cursor")
    assert (home / "config.toml").read_text(encoding="utf-8") == before


def test_the_command_line(home, monkeypatch, capsys):
    monkeypatch.setenv("MILO_HOME", str(home))
    assert install.main(["configure", "--harness", "claude"]) == 0
    assert "works with claude" in capsys.readouterr().out
    assert install.main(["configure", "--chat", "nope"]) == 2
