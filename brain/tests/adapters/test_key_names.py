"""Keys read the way the user's own keyboard names them, in Settings and in key hints."""
from milo.adapters.platform import LINUX, MACOS, WINDOWS
from milo.adapters.key_names import MAC_KEY_NAMES, PC_KEY_NAMES


def test_pc_keys_use_pc_names():
    assert [PC_KEY_NAMES.key(k) for k in ("right_option", "right_control", "right_command")] == [
        "Right Alt", "Right Ctrl", "Right Windows"]
    assert PC_KEY_NAMES.combo("ctrl+option+m") == "Ctrl+Alt+M"
    assert PC_KEY_NAMES.combo("Control+Shift+N") == "Ctrl+Shift+N"
    assert PC_KEY_NAMES.combo("") == "Off"


def test_the_mac_keeps_its_names():
    assert MAC_KEY_NAMES.key("right_option") == "Right Option"
    assert MAC_KEY_NAMES.combo("ctrl+option+m") == "Control-Option-M"


def test_each_platform_has_its_keyboard():
    assert MACOS.key_names is MAC_KEY_NAMES and WINDOWS.key_names is PC_KEY_NAMES
    assert LINUX.key_names.key("right_command") == "Right Super" and LINUX.key_names.combo("ctrl+option+n") == "Ctrl+Alt+N"


def test_settings_report_labels_keys_for_the_running_platform(tmp_path):
    from milo.config import Config
    from milo.settings import Settings

    class File:
        def read(self):
            return Config({}, WINDOWS)

    sent = []
    report = Settings(File(), Config({}, WINDOWS), type("Sink", (), {"emit": lambda self, e: sent.append(e)})(),
                      {}).report()
    rows = {(r["section"], r["key"]): r for r in report.settings}
    assert "Right Alt" in rows["ui", "talk_key"]["labels"]
    assert rows["ui", "whats_this_key"]["labels"] == ["Ctrl+Alt+M", "Ctrl+Alt+W", "Ctrl+Shift+M", "Off"]
    assert rows["ui", "meeting_key"]["labels"][0] == "Ctrl+Alt+N"
    assert not any("Option" in label for row in report.settings for label in row["labels"])
