"""Which computer-use actions may run on their own, which wait for the user's yes, and which never run.

Pure: it reads the tool, its arguments and what the app said the action would touch (`target`, from the
describe step: app, title, role, secure). It errs towards asking. A button or script that mentions
sending, deleting, paying and the like asks first; password fields, the keychain and security settings
are off limits.
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
_SHELL = re.compile(r"\bdo\s+shell\s+script\b", re.IGNORECASE)
_SECURITY_APPS = ("System Settings", "System Preferences", "Systemeinstellungen", "Keychain Access",
                  "Schlüsselbundverwaltung", "Passwords", "Passwörter")
_SECURITY_WORDS = re.compile(r"(privacy|security|datenschutz|sicherheit|filevault|firewall|password|passwort)",
                             re.IGNORECASE)

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
    app = str(target.get("app") or "")
    title = " ".join(str(target.get(k) or "") for k in ("title", "description")).strip()
    if tool in ("type", "ax_set_value") and target.get("secure"):
        return Verdict(Risk.NEVER, "a password field")
    if tool in ("click", "ax_press", "ax_set_value", "type", "key") and _security_setting(app, title):
        return Verdict(Risk.NEVER, "a security setting")
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
        if _SHELL.search(script):
            return Verdict(Risk.ASK, "a shell command")
        return _words(script)
    return OK


def _words(text: str) -> Verdict:
    m = _RISKY.search(text)
    return Verdict(Risk.ASK, m.group(1).lower()) if m else OK


def _security_setting(app: str, title: str) -> bool:
    if app in ("Keychain Access", "Schlüsselbundverwaltung", "Passwords", "Passwörter"):
        return True
    return app in _SECURITY_APPS and bool(_SECURITY_WORDS.search(title))
