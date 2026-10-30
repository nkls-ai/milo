"""Which computer-use actions may run on their own, which wait for the user's yes, and which never run.

Pure: it reads the tool, its arguments and what the app said the action would touch (`target`, from the
describe step: app, title, role, secure). It errs towards asking. A button or script that mentions
sending, deleting, paying and the like asks first, and so does anything that could run code: typing into a
terminal, AppleScript that runs a shell, UI scripting or other scripts, and any change in System Settings.
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
    "close account", "delete account",
    # German, since Milo's users speak it too.
    "senden", "absenden", "abschicken", "löschen", "entfernen", "kaufen", "jetzt kaufen", "bezahlen", "zahlen",
    "bestellen", "kostenpflichtig bestellen", "überweisen", "papierkorb leeren", "verwerfen", "ersetzen",
    "kündigen", "veröffentlichen", "bestätigen",
)
_RISKY = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in sorted(_RISKY_WORDS, key=len, reverse=True))
                    + r")(?!\w)", re.IGNORECASE)
_SECRET = re.compile(r"(?<!\w)(password|passwort|kennwort|passcode|keychain|schlüsselbund)(?!\w)", re.IGNORECASE)
# Scripts that run code or type anywhere: a shell, another script, raw Apple events, UI scripting, terminals.
_CODE = re.compile(r"\b(do\s+shell\s+script|do\s+script|run\s+script|load\s+script|osascript|system\s+events)\b|«event"
                   r"|application\s+\"(terminal|iterm2?|warp|ghostty|script editor|automator|shortcuts)\"",
                   re.IGNORECASE)
_SETTINGS_APPS = ("system settings", "system preferences", "systemeinstellungen")
_SECRET_APPS = ("keychain access", "schlüsselbundverwaltung", "passwords", "passwörter")
_SECURITY_WORDS = re.compile(r"(privacy|security|datenschutz|sicherheit|filevault|firewall|password|passwort"
                             r"|login items|anmeldeobjekte|users|benutzer)", re.IGNORECASE)
# Typing into these runs commands.
_CODE_APPS = ("terminal", "iterm", "iterm2", "warp", "ghostty", "alacritty", "kitty", "wezterm", "hyper",
              "script editor", "skripteditor", "automator", "shortcuts", "kurzbefehle")

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


def classify(tool: str, args: dict, target: dict) -> Verdict:
    app = str(target.get("app") or "").strip().lower()
    title = " ".join(str(target.get(k) or "") for k in ("title", "description")).strip()
    if tool in ("type", "ax_set_value") and target.get("secure"):
        return Verdict(Risk.NEVER, "a password field")
    if tool in ("click", "ax_press", "ax_set_value", "type", "key", "scroll"):
        if app in _SECRET_APPS or (app in _SETTINGS_APPS and _SECURITY_WORDS.search(title)):
            return Verdict(Risk.NEVER, "a security setting")
        if app in _SETTINGS_APPS:
            return Verdict(Risk.ASK, "change a system setting")
    if tool == "open_app" and str(args.get("name", "")).strip().lower() in _CODE_APPS:
        return Verdict(Risk.ASK, "open a program that runs commands")
    if tool in ("type", "key", "ax_set_value") and app in _CODE_APPS:
        return Verdict(Risk.ASK, "run a command")
    if tool in ("click", "ax_press"):
        return _words(title)
    if tool == "key":
        combo = normalize_combo(str(args.get("combo", "")))
        if combo in _RISKY_COMBOS:
            return Verdict(Risk.ASK, _RISKY_COMBOS[combo])
        if combo in _PRESS_KEYS:
            return _words(title)  # return on a focused "Send" button sends
        return OK
    if tool == "run_applescript":
        script = str(args.get("script", ""))
        if _SECRET.search(script):
            return Verdict(Risk.NEVER, "passwords")
        if _CODE.search(script):
            return Verdict(Risk.ASK, "run other programs or type for you")
        return _words(script)
    return OK


def _words(text: str) -> Verdict:
    m = _RISKY.search(text)
    return Verdict(Risk.ASK, m.group(1).lower()) if m else OK
