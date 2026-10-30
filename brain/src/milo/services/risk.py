"""Which computer-use actions may run on their own, which wait for the user's yes, and which never run.

Pure: it reads the tool, its arguments and what the app said the action would touch (`target`, from the
describe step: app, title, role, secure). It errs towards asking where it matters and stays quiet for what
can be undone: opening an app, reading, making a new document and filling it never ask. A button that
mentions sending, deleting, paying and the like asks first, and so does anything that could run code: a
script that isn't plainly about a new document, typing into a terminal, and any change in System Settings.
Replacing filled cells asks. A careful task (from a conversation that read the screen) asks before every
script and every change to a document it didn't make.
Password fields, the keychain and security settings are off limits. A word list can be talked around by a
determined agent; it is a brake, not a sandbox, so everything the worker does also shows in the Milo
window and stops when the user touches the mouse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Risk(StrEnum):
    OK = "ok"
    ASK = "ask"
    NEVER = "never"


@dataclass(frozen=True)
class Verdict:
    risk: Risk
    reason: str = ""
    """The word or thing that made it risky, for the question and the log."""


OK = Verdict(Risk.OK)

_RISKY_WORDS = (
    "send", "send now", "delete", "remove", "erase", "buy", "buy now", "purchase", "pay", "checkout", "check out",
    "order", "place order", "submit", "transfer", "withdraw", "empty trash", "empty bin", "discard", "overwrite",
    "replace", "uninstall", "unsubscribe", "publish", "post", "confirm", "sell", "cancel subscription",
    "close account", "delete account", "share", "trash",
    # German, since Milo's users speak it too.
    "senden", "absenden", "abschicken", "löschen", "entfernen", "kaufen", "jetzt kaufen", "bezahlen", "zahlen",
    "bestellen", "kostenpflichtig bestellen", "überweisen", "papierkorb leeren", "verwerfen", "ersetzen",
    "kündigen", "veröffentlichen", "bestätigen", "teilen",
)
# Words in a script that change or close what is already there. A script with none of these that only talks
# to document apps and makes a new document is safe to run without asking.
_SCRIPT_CHANGES = re.compile(r"(?<!\w)(save|close|quit|clear|move|duplicate|print|set\s+name|open\s+(?:file|POSIX|alias)"
                             r"|export|activate\s+window)(?!\w)", re.IGNORECASE)
_SCRIPT_NEW = re.compile(r"\bmake\s+new\s+(document|workbook|presentation|slide|table|sheet|paragraph|word"
                         r"|text|row|column)\b", re.IGNORECASE)
_SCRIPT_WRITES = re.compile(r"(?<!\w)(set|make|delete|remove|insert|paste|copy|duplicate)(?!\w)", re.IGNORECASE)
_TELL_APP = re.compile(r'\btell\s+(?:application|app)\s+(?:id\s+)?"([^"]+)"', re.IGNORECASE)
# Apps whose documents a script may make and fill without asking.
DOCUMENT_APPS = ("textedit", "pages", "keynote", "numbers", "microsoft excel", "microsoft word",
                 "microsoft powerpoint", "com.apple.textedit", "com.apple.iwork.pages", "com.apple.iwork.keynote",
                 "com.apple.iwork.numbers", "com.microsoft.excel", "com.microsoft.word", "com.microsoft.powerpoint")
_RISKY = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in sorted(_RISKY_WORDS, key=len, reverse=True))
                    + r")(?!\w)", re.IGNORECASE)
_SECRET = re.compile(r"(?<!\w)(password|passwort|kennwort|passcode|keychain|schlüsselbund)(?!\w)", re.IGNORECASE)
# Only for wording the question; every script asks anyway.
_CODE = re.compile(r"\b(do\s+shell\s+script|do\s+script|do\s+javascript|run\s+script|load\s+script|osascript"
                   r"|use\s+framework|current\s+application|system\s+events|keystroke|key\s+code)\b|«",
                   re.IGNORECASE)
_SETTINGS_APPS = ("system settings", "system preferences", "systemeinstellungen", "com.apple.systempreferences")
# Password managers, the same list as AX.secretApps in the app.
_SECRET_APPS = ("keychain access", "schlüsselbundverwaltung", "passwords", "passwörter", "1password", "1password 7",
                "bitwarden", "lastpass", "dashlane", "keepassxc", "com.apple.keychainaccess", "com.apple.passwords",
                "com.1password.1password", "com.agilebits.onepassword7", "com.bitwarden.desktop",
                "com.lastpass.lastpass", "com.dashlane.dashlanephonefinal", "org.keepassxc.keepassxc")
_SECURITY_WORDS = re.compile(r"(privacy|security|datenschutz|sicherheit|filevault|firewall|password|passwort"
                             r"|login items|anmeldeobjekte|users|benutzer)", re.IGNORECASE)
# Typing into these runs commands.
_CODE_APPS = ("terminal", "iterm", "iterm2", "warp", "ghostty", "alacritty", "kitty", "wezterm", "hyper",
              "script editor", "skripteditor", "automator", "shortcuts", "kurzbefehle", "com.apple.terminal",
              "com.googlecode.iterm2", "dev.warp.warp-stable", "com.mitchellh.ghostty", "org.alacritty",
              "net.kovidgoyal.kitty", "com.github.wez.wezterm", "co.zeit.hyper", "com.apple.scripteditor2",
              "com.apple.automator", "com.apple.shortcuts")

_MODIFIER_ORDER = ("ctrl", "option", "shift", "cmd")
_ALIASES = {"command": "cmd", "⌘": "cmd", "control": "ctrl", "⌃": "ctrl", "alt": "option", "opt": "option",
            "⌥": "option", "⇧": "shift", "backspace": "delete", "enter": "return", "esc": "escape"}
# Shortcuts that send or delete in common Mac apps.
_RISKY_COMBOS = {
    "cmd+delete": "delete", "cmd+forwarddelete": "delete", "shift+cmd+delete": "empty trash",
    "option+shift+cmd+delete": "empty trash", "cmd+return": "send", "shift+cmd+d": "send",
    "ctrl+cmd+return": "send", "option+cmd+delete": "delete",
}
_PRESS_KEYS = ("return", "space", "keypadenter")


def normalize_combo(combo: str) -> str:
    """"Command+Shift+S" -> "shift+cmd+s": lower case, known aliases, modifiers in a fixed order."""
    parts = [_ALIASES.get(p, p) for p in (p.strip().lower() for p in combo.replace("-", "+").split("+")) if p]
    mods = [m for m in _MODIFIER_ORDER if m in parts]
    keys = [p for p in parts if p not in _MODIFIER_ORDER]
    return "+".join(mods + keys)


def app_names(*names: object) -> set[str]:
    """Display names and bundle ids, lower case, without a path or ".app", so "/Applications/Terminal.app",
    "Terminal" and "com.apple.Terminal" all match."""
    out = set()
    for name in names:
        text = str(name or "").strip().rstrip("/").rsplit("/", 1)[-1].lower().removesuffix(".app").strip()
        if text:
            out.add(text)
    return out


def classify(tool: str, args: dict, target: dict, *, careful: bool = False) -> Verdict:
    apps = app_names(target.get("app"), target.get("bundle"))
    title = " ".join(str(target.get(k) or "") for k in ("title", "description")).strip()
    if tool in ("type", "ax_set_value") and target.get("secure"):
        return Verdict(Risk.NEVER, "a password field")
    if tool in ("click", "ax_press", "ax_set_value", "type", "key", "scroll"):
        if apps & set(_SECRET_APPS) or (apps & set(_SETTINGS_APPS) and _SECURITY_WORDS.search(title)):
            return Verdict(Risk.NEVER, "a security setting")
        if apps & set(_SETTINGS_APPS):
            return Verdict(Risk.ASK, "change a system setting")
    if tool == "open_app":
        opening = app_names(args.get("name"), target.get("bundle"))
        if opening & set(_SECRET_APPS):
            return Verdict(Risk.NEVER, "a security setting")
        if opening & set(_CODE_APPS):
            return Verdict(Risk.ASK, "open a program that runs commands")
    if tool in ("type", "key", "ax_set_value") and apps & set(_CODE_APPS):
        return Verdict(Risk.ASK, "run a command")
    if tool in ("click", "ax_press"):
        if target.get("unresolved"):
            return Verdict(Risk.ASK, "click something I can't name")
        return _words(title)
    if tool == "key":
        combo = normalize_combo(str(args.get("combo", "")))
        if combo in _RISKY_COMBOS:
            return Verdict(Risk.ASK, _RISKY_COMBOS[combo])
        if combo in _PRESS_KEYS:
            return _words(title)  # return on a focused "Send" button sends
        return OK
    if tool == "sheet_write":
        if target.get("new") or target.get("made"):
            return OK  # a document Milo made in this task
        if int(target.get("filled") or 0) > 0:
            return Verdict(Risk.ASK, "overwrite")
        return Verdict(Risk.ASK, "change") if careful else OK
    if tool == "run_applescript":
        # A word list can't tell what a script does (strings can be built, apps named in variables), so only
        # a script that plainly makes a new document in a document app runs on its own. Scripts about
        # passwords never run.
        script = str(args.get("script", ""))
        if _SECRET.search(script):
            return Verdict(Risk.NEVER, "passwords")
        if _CODE.search(script):
            return Verdict(Risk.ASK, "run other programs or type for you")
        risky = _words(script)
        if risky.risk is Risk.ASK:
            return risky
        return OK if not careful and new_document_script(script) else Verdict(Risk.ASK, "run a script")
    return OK


def new_document_script(script: str) -> bool:
    """The script talks only to document apps, makes a new document, and changes nothing that was there.

    Writing (`set`, `make`) is fine after `make new document`; saving, closing, moving and the like are not.
    A script that writes without making a new document could be changing one of the user's own.
    """
    told = app_names(*_TELL_APP.findall(script))
    if not told or not told <= set(DOCUMENT_APPS) or "«" in script:
        return False
    if _SCRIPT_CHANGES.search(script):
        return False
    return bool(_SCRIPT_NEW.search(script)) or not _SCRIPT_WRITES.search(script)


def _words(text: str) -> Verdict:
    m = _RISKY.search(text)
    return Verdict(Risk.ASK, m.group(1).lower()) if m else OK
