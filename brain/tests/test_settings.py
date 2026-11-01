"""The Settings window's side of the brain: report, validate, save and apply."""

from milo.config import Config
from milo.core.events import SettingsReport
from milo.services.ui_state import UiState
from milo.settings import SETTINGS, Settings
from tests.fakes import MemoryConfigFile, RecordingSink
import pytest


def make(raw: dict | None = None):
    file, sink, applied = MemoryConfigFile(raw), RecordingSink(), []
    live = {("ui", "talk_key"): lambda c: applied.append(c.ui.talk_key)}
    return Settings(file, file.read(), UiState(sink), live), file, sink, applied


def rows(report: SettingsReport) -> dict:
    return {(r["section"], r["key"]): r for r in report.settings}


def test_the_report_has_every_setting_with_its_value_options_and_labels():
    settings, _, sink, _ = make({"ui": {"talk_key": "right_command"}})
    settings.send()
    [report] = sink.of(SettingsReport)
    table = rows(report)
    assert set(table) == {(s.section, s.key) for s in SETTINGS}
    assert table["ui", "talk_key"]["value"] == "right_command" and "fn" in table["ui", "talk_key"]["options"]
    assert ("ui", "character") not in table
    assert table["dictation", "stream"]["options"] == ["off", "preview", "type"]
    assert table["chat", "updates"]["value"] == "bubble" and table["chat", "updates"]["live"] is False
    assert table["ui", "voice"] == {"section": "ui", "key": "voice", "value": True, "options": [], "labels": [],
                                    "live": False}
    assert table["ui", "hide_after_s"]["value"] == 15 and table["ui", "hide_after_s"]["options"] == [15, 30, 60, 300, 0]
    assert table["ui", "hide_after_s"]["labels"] == ["After 15 seconds", "After 30 seconds", "After a minute", "After 5 minutes", "Never"]
    assert all(len(r["options"]) == len(r["labels"]) for r in report.settings)


def test_a_live_change_is_saved_and_applied_without_a_restart():
    settings, file, sink, applied = make()
    settings.change("ui", "talk_key", "right_control")
    assert file.raw["ui"]["talk_key"] == "right_control" and applied == ["right_control"]
    [report] = sink.of(SettingsReport)
    assert rows(report)["ui", "talk_key"]["value"] == "right_control" and not report.restart


def test_any_other_change_waits_for_a_restart_until_it_is_changed_back():
    settings, _, sink, applied = make()
    settings.change("chat", "updates", "chatty")
    assert sink.of(SettingsReport)[-1].restart and applied == []
    settings.change("chat", "updates", "bubble")
    assert not sink.of(SettingsReport)[-1].restart


def test_a_bad_value_is_not_saved_and_the_error_is_in_plain_words():
    settings, file, sink, applied = make()
    settings.change("ui", "talk_key", "fn")
    settings.change("ui", "talk_key", "caps_lock")
    first, second = sink.of(SettingsReport)
    assert first.error == "The dictate key and the talk key need to be different keys."
    assert second.error == "Milo couldn't use that. Try one of the choices."
    assert file.writes == [] and applied == []
    assert rows(second)["ui", "talk_key"]["value"] == "right_option"


def test_only_the_listed_settings_can_be_changed():
    settings, file, sink, _ = make()
    settings.change("hands", "enabled", False)
    assert file.writes == [] and sink.of(SettingsReport)[0].error == "That one can't be changed here."


def test_a_broken_file_is_reported_without_rows():
    class Broken(MemoryConfigFile):
        def read(self) -> Config:
            raise OSError("gone")

    file, sink = Broken(), RecordingSink()
    Settings(file, Config({}), UiState(sink), {}).send()
    [report] = sink.of(SettingsReport)
    assert report.settings == [] and "settings file" in report.error


@pytest.mark.parametrize("provider", ["claude_live", "codex_live", "openai_compat", "none"])
def test_talking_provider_is_saved_explicitly_and_requires_restart(provider):
    settings, file, sink, applied = make({"chat": {"use": "claude_live"}})
    settings.send()
    assert file.writes == []
    row = rows(sink.of(SettingsReport)[-1])["chat", "use"]
    assert row["options"] == ["claude_live", "codex_live", "openai_compat", "none"]
    assert row["labels"] == ["Claude CLI", "Codex CLI", "OpenAI-compatible", "Dictation only"]
    assert not row["live"]
    settings.change("chat", "use", provider)
    report = sink.of(SettingsReport)[-1]
    assert file.raw["chat"]["use"] == provider
    assert rows(report)["chat", "use"]["value"] == provider
    assert report.restart is (provider != "claude_live")
    assert applied == []
    settings.change("chat", "use", "claude_live")
    assert not sink.of(SettingsReport)[-1].restart


@pytest.mark.parametrize("provider", ["missing_provider", "", False, ["codex_live"]])
def test_unknown_talking_provider_is_refused_before_writing(provider):
    settings, file, sink, _ = make({"chat": {"use": "claude_live"}})
    settings.change("chat", "use", provider)
    assert file.writes == []
    assert sink.of(SettingsReport)[-1].error


def test_talking_provider_preserves_real_config_comments_and_other_settings(tmp_path):
    from milo.config_file import TomlConfigFile
    path = tmp_path / "config.toml"
    path.write_text('# My settings\n[chat]\nuse = "claude_live" # talking model\nupdates = "chatty"\n'
                    '[chat.openai_compat]\nmodel = "my-model"\n', encoding="utf-8")
    file, sink = TomlConfigFile(path), RecordingSink()
    settings = Settings(file, file.read(), UiState(sink), {})
    original = path.read_text(encoding="utf-8")
    settings.report()
    assert path.read_text(encoding="utf-8") == original
    settings.change("chat", "use", "codex_live")
    text = path.read_text(encoding="utf-8")
    assert '# My settings' in text and '# talking model' in text
    assert 'use = "codex_live"' in text and 'updates = "chatty"' in text
    assert '[chat.openai_compat]' in text and 'model = "my-model"' in text
    assert sink.of(SettingsReport)[-1].restart
