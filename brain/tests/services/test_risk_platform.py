import pytest

from milo.adapters.risk_policy import LINUX, MACOS, WINDOWS, for_platform
from milo.services.risk import Risk, app_names, classify, normalize_combo, plain_app


@pytest.mark.parametrize("policy,app", [
    (WINDOWS, "PowerShell"), (WINDOWS, "pwsh.exe"), (WINDOWS, "cmd.exe"),
    (WINDOWS, "Windows Terminal"), (WINDOWS, "WindowsTerminal.exe"),
    (WINDOWS, r"C:\Windows\System32\cmd.exe"),
    (LINUX, "gnome-terminal"), (LINUX, "Konsole"), (LINUX, "/usr/bin/xterm"),
])
@pytest.mark.parametrize("tool,args", [("type", {"text": "anything"}), ("key", {"combo": "return"}),
                                        ("ax_set_value", {"text": "anything"})])
def test_terminal_actions_always_ask_and_cannot_receive_persistent_allow(policy, app, tool, args):
    verdict = classify(tool, args, {"app": app, "role": "text field"}, policy)
    assert verdict.risk is Risk.ASK and verdict.reason == "run a command"
    assert not plain_app(app, policy=policy)


@pytest.mark.parametrize("policy", [WINDOWS, LINUX])
@pytest.mark.parametrize("combo,reason", [
    ("Ctrl+Enter", "send"), ("cmd+enter", "send"), ("Command+Shift+D", "send"),
    ("Ctrl+Shift+D", "send"), ("alt+s", "send"),
    ("Shift+Delete", "delete it for good"), ("shift+del", "delete it for good"),
    ("Control+Shift+Delete", "delete browsing data"),
])
def test_irreversible_pc_shortcuts_never_become_document_work(policy, combo, reason):
    verdict = classify("key", {"combo": combo}, {"app": "Outlook", "role": "text field"}, policy)
    assert verdict.risk is Risk.ASK and verdict.reason == reason


@pytest.mark.parametrize("policy,app", [(WINDOWS, "File Explorer"), (LINUX, "Nautilus")])
def test_pc_file_delete_is_reversible_but_shift_delete_is_not(policy, app):
    target = {"app": app, "role": "list item", "title": "selected file"}
    assert classify("key", {"combo": "delete"}, target, policy).risk is Risk.UNDO
    assert classify("key", {"combo": "shift+delete"}, target, policy).risk is Risk.ASK
    assert not plain_app(app, policy=policy)


@pytest.mark.parametrize("policy,app", [(WINDOWS, "Settings"), (LINUX, "gnome-control-center")])
def test_system_settings_and_security_are_not_covered_by_an_app_allow(policy, app):
    assert not plain_app(app, policy=policy)
    assert classify("click", {}, {"app": app, "title": "Wallpaper"}, policy).risk is Risk.ASK
    assert classify("click", {}, {"app": app, "title": "Privacy and Security"}, policy).risk is Risk.NEVER


def test_mac_normalization_and_defaults_remain_unchanged():
    assert normalize_combo("Command+Shift+Backspace", MACOS) == "shift+cmd+delete"
    assert normalize_combo("Command+Shift+Backspace") == "shift+cmd+delete"
    assert classify("key", {"combo": "cmd+return"}, {}, MACOS).reason == "send"
    assert classify("key", {"combo": "cmd+shift+delete"}, {}, MACOS).reason == "empty the Trash"
    assert for_platform("macos") is MACOS


def test_pc_normalization_matches_the_effective_physical_keys():
    assert normalize_combo("cmd+shift+delete", WINDOWS) == "ctrl+shift+forwarddelete"
    assert normalize_combo("command+backspace", WINDOWS) == "ctrl+backspace"
    assert normalize_combo("control+alt+enter", LINUX) == "ctrl+option+return"
    assert app_names(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe") == {"powershell"}


def test_pc_confirmation_names_the_physical_keys_it_will_press():
    from milo.services.hands import confirm_question, title
    args = {"combo": "Command+Shift+Delete"}
    assert "Ctrl+Shift+Delete" in title("key", args, {}, WINDOWS)
    question = confirm_question("key", args, {}, "delete browsing data", policy=WINDOWS)
    assert "Ctrl+Shift+Delete" in question and "⌘" not in question


@pytest.mark.parametrize("policy,app", [(WINDOWS, "Windows Security"), (LINUX, "Seahorse")])
def test_platform_password_stores_are_never_controllable(policy, app):
    assert classify("key", {"combo": "return"}, {"app": app}, policy).risk is Risk.NEVER
    assert not plain_app(app, policy=policy)
