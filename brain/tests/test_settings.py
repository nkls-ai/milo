"""The Settings window's side of the brain: report, validate, save and apply."""

from milo.config import Config
from milo.core.events import SettingsReport
from milo.services.ui_state import UiState
from milo.settings import SETTINGS, Settings
from tests.fakes import MemoryConfigFile, RecordingSink


def make(raw: dict | None = None):
    file, sink, applied = MemoryConfigFile(raw), RecordingSink(), []
    live = {("ui", "character"): lambda c: applied.append(c.ui.character)}
    return Settings(file, file.read(), UiState(sink), live), file, sink, applied


def rows(report: SettingsReport) -> dict:
    return {(r["section"], r["key"]): r for r in report.settings}


def test_the_report_has_every_setting_with_its_value_options_and_labels():
    settings, _, sink, _ = make({"ui": {"character": "kit"}})
    settings.send()
    [report] = sink.of(SettingsReport)
    table = rows(report)
    assert set(table) == {(s.section, s.key) for s in SETTINGS}
    assert table["ui", "character"]["value"] == "kit" and "dragon" in table["ui", "character"]["options"]
    assert table["dictation", "stream"]["options"] == ["off", "preview", "type"]
    assert table["chat", "updates"]["value"] == "bubble" and table["chat", "updates"]["live"] is False
    assert table["ui", "voice"] == {"section": "ui", "key": "voice", "value": True, "options": [], "labels": [],
                                    "live": False}
    assert all(len(r["options"]) == len(r["labels"]) for r in report.settings)


def test_a_live_change_is_saved_and_applied_without_a_restart():
    settings, file, sink, applied = make()
    settings.change("ui", "character", "glow")
    assert file.raw["ui"]["character"] == "glow" and applied == ["glow"]
    [report] = sink.of(SettingsReport)
    assert rows(report)["ui", "character"]["value"] == "glow" and not report.restart


def test_any_other_change_waits_for_a_restart_until_it_is_changed_back():
    settings, _, sink, applied = make()
    settings.change("chat", "updates", "chatty")
    assert sink.of(SettingsReport)[-1].restart and applied == []
    settings.change("chat", "updates", "bubble")
    assert not sink.of(SettingsReport)[-1].restart


def test_a_bad_value_is_not_saved_and_the_error_is_in_plain_words():
    settings, file, sink, applied = make()
    settings.change("ui", "talk_key", "fn")
    settings.change("ui", "character", "unicorn")
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
