"""Which computer-use actions may run on their own, which wait for the user's yes, and which never run.

Pure: it reads the tool, its arguments and what the app said the action would touch (`target`, from the
describe step: app, title, role, secure). The line is whether the action can be undone (ADR 0023):

- Opening an app, reading, and making a new document with sheet_write or write_document never ask.
- What can be undone (moving files or mail to the Trash, deleting a note, which Notes keeps in Recently Deleted)
  is `UNDO`: it asks only in "Every step" mode.
- Work inside an open document (replacing filled cells, a script that stays in one app) asks once per task, and
  not at all in auto mode (ADR 0022).
- What can't be undone asks every time, in every mode: emptying the Trash, deleting for good, Don't Save,
  replacing a file on disk, uninstalling, closing an account, cancelling a subscription, sending, sharing and
  publishing. A delete button in an app Milo doesn't know asks too, since it may be for good. So does anything
  that could run code: every free-form AppleScript, typing into a terminal, and any change in System Settings.
- Buying and anything else with money is `MONEY`: it asks every time, and only a click on Yes answers it.
- Password fields, card-number and security-code fields, the keychain and security settings are off limits.

A word list can be talked around by a determined agent; it is a brake, not a sandbox, so everything the worker
does also shows in the Milo window and stops when the user touches the mouse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Risk(StrEnum):
    OK = "ok"
    UNDO = "undo"
    """It can be undone (the Trash, Recently Deleted): asks only in "Every step" mode."""
    ASK = "ask"
    MONEY = "money"
    """Buying, paying, moving money: asks every time, and only a click on Yes counts."""
    NEVER = "never"


@dataclass(frozen=True)
class Verdict:
    risk: Risk
    reason: str = ""
    """The word or thing that made it risky, for the question and the log."""


OK = Verdict(Risk.OK)

_MONEY_WORDS = (
    "buy", "buy now", "purchase", "pay", "pay now", "checkout", "check out", "order", "place order", "transfer",
    "withdraw", "sell", "kaufen", "jetzt kaufen", "bezahlen", "jetzt bezahlen", "zahlen", "bestellen",
    "kostenpflichtig bestellen", "überweisen", "überweisung", "verkaufen", "abheben",
)
# Can't be undone: these ask every time, whatever the mode.
_FOR_GOOD_WORDS = (
    "send", "send now", "submit", "publish", "post", "share", "confirm", "senden", "absenden", "abschicken",
    "veröffentlichen", "teilen", "bestätigen",
    "empty trash", "empty bin", "empty the trash", "papierkorb leeren", "delete immediately", "delete permanently",
    "delete forever", "sofort löschen", "endgültig löschen", "erase", "don't save", "don’t save",
    "do not save", "nicht sichern", "nicht speichern", "discard", "discard changes", "verwerfen", "overwrite",
    "überschreiben", "replace", "ersetzen", "uninstall", "deinstallieren", "unsubscribe", "abbestellen",
    "cancel subscription", "abo kündigen", "kündigen", "close account", "delete account", "konto löschen",
    "delete", "remove", "löschen", "entfernen", "trash",
)
# Moving something to the Trash can always be undone, in any app.
_TRASH_WORDS = ("move to trash", "move to the trash", "move to bin", "in den papierkorb", "in den papierkorb legen")
_RISKY_WORDS = _MONEY_WORDS + _FOR_GOOD_WORDS + _TRASH_WORDS
_MONEY_SET = frozenset(_MONEY_WORDS)
_TRASH_SET = frozenset(_TRASH_WORDS)
_RISKY = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in sorted(set(_RISKY_WORDS), key=len, reverse=True))
                    + r")(?!\w)", re.IGNORECASE)
# Apps where a plain "Delete" keeps what it deletes: Notes (Recently Deleted), Mail (the Trash mailbox), Photos
# (Recently Deleted) and Finder (the Trash). Only these exact labels count, so "Delete Mailbox", "Delete Account" or
# "Delete…" (a dialog follows, often because it is for good) there still ask every time.
_TRASH_APPS = ("notes", "notizen", "com.apple.notes", "mail", "com.apple.mail", "photos", "fotos",
               "com.apple.photos", "finder", "com.apple.finder")
_TRASH_LABEL = re.compile(r"^\s*(delete|löschen|trash|in den papierkorb)(\s+(\d+\s+)?(note|notes|notiz|notizen|message"
                          r"|messages|e-?mails?|photos?|videos?|items?|objekte?|fotos?))?\s*$",
                          re.IGNORECASE)
# Documents where deleting cells, rows or text is undone with ⌘Z: work inside the document (ADR 0022's scope).
_DOCUMENT_APPS = ("microsoft excel", "com.microsoft.excel", "numbers", "com.apple.iwork.numbers", "pages",
                  "com.apple.iwork.pages", "keynote", "com.apple.iwork.keynote", "microsoft word",
                  "com.microsoft.word", "microsoft powerpoint", "com.microsoft.powerpoint", "textedit",
                  "com.apple.textedit")
_DOCUMENT_EDIT = re.compile(r"^\s*(delete|löschen|clear|clear contents|inhalte löschen|cut|ausschneiden|replace all"
                            r"|alle ersetzen|replace & find|delete (rows?|columns?|cells?|text)|(zeilen|spalten|zellen)"
                            r" löschen)\s*(…|\.\.\.)?\s*$", re.IGNORECASE)
# A web page writes its own labels, so "Move to Trash" there is only the page's word for it: it asks.
_BROWSERS = ("safari", "google chrome", "chrome", "firefox", "arc", "microsoft edge", "brave browser", "opera",
             "com.apple.safari", "com.google.chrome", "org.mozilla.firefox", "company.thebrowser.browser",
             "com.microsoft.edgemac", "com.brave.browser", "com.operasoftware.opera")
# Where the focus is when Delete only deletes text.
_TEXT_ROLES = ("text field", "text area", "search field", "combo box", "password field", "text entry area")
_BARE_DELETE = re.compile(r"^\s*(delete|löschen)\s*(…|\.\.\.)?\s*$", re.IGNORECASE)
# Card numbers and security codes: never typed, like passwords.
_CARD = re.compile(r"(card\s*number|kartennummer|credit\s*card|kreditkarte|\bcvv2?\b|\bcvc2?\b|security\s*code"
                   r"|sicherheitscode|prüfnummer|kartenprüf)", re.IGNORECASE)

_SECRET = re.compile(r"(?<!\w)(password|passwort|kennwort|passcode|keychain|schlüsselbund)(?!\w)", re.IGNORECASE)
# Only for wording the question; every script asks anyway.
_CODE = re.compile(r"\b(do\s+shell\s+script|do\s+script|do\s+javascript|run\s+script|load\s+script|osascript"
                   r"|do\s+visual\s+basic|run\s+vb\s+macro"
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
# Shortcuts that send or delete in common Mac apps. ⌘⌫ moves to the Trash (Finder, Mail, Photos, Notes) or deletes
# text, which ⌘Z undoes; ⌥⌘⌫ deletes for good, ⇧⌘⌫ empties the Trash.
_RISKY_COMBOS = {
    "cmd+delete": "move to the Trash", "cmd+forwarddelete": "move to the Trash", "shift+cmd+delete": "empty the Trash",
    "option+shift+cmd+delete": "empty the Trash", "cmd+return": "send", "shift+cmd+d": "send",
    "ctrl+cmd+return": "send", "option+cmd+delete": "delete it for good",
}
UNDO_REASONS = frozenset({"move to the Trash", "delete a note", "delete"})
"""Reasons for an UNDO verdict, for the question and the log."""
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


WORK = frozenset({"run a script", "replace cells", "change the document", "use"})
"""Reasons that are about the work in the app itself. An Allow covers them for the rest of the task, and Allow
always for that app (ADR 0022). Sending, deleting for good, buying, code and settings are not among them: they ask
every time."""


# What a script may not do for an Allow to cover it: write or open files and links itself, or work in Finder.
_SCRIPT_REACH = re.compile(r"\b(open\s+for\s+access|write|set\s+eof|open|location|store\s+script|posix\s+file"
                           r"|alias|path\s+to|choose\s+file|mount\s+volume|delete|move|duplicate|save|export|print"
                           r"|file|folder|url|close|quit|read|info\s+for|list\s+(disk|folder))\b|\"[/~]|https?:|://"
                           r'|"[^"\n]*:[^"\n]*:[^"\n]*"', re.IGNORECASE)  # the last: an HFS path, "Disk:Users:me"
_FILE_APPS = ("finder", "com.apple.finder", "path finder", "forklift", "commander one")


def coverable_script(script: str) -> bool:
    """A script an Allow for its app may cover: it does nothing outside the document in front, as far as words can
    tell (no files, paths, links, saving, opening or closing). A brake, not a sandbox, like the rest of this file."""
    return not _SCRIPT_REACH.search(script)


def plain_app(name: str, bundle: str = "") -> bool:
    """An app an Allow may cover: not a password manager, System Settings or a program that runs commands."""
    names = app_names(name, bundle)
    return bool(names) and not names & set(_SECRET_APPS + _SETTINGS_APPS + _CODE_APPS + _FILE_APPS)


def classify(tool: str, args: dict, target: dict) -> Verdict:
    apps = app_names(target.get("app"), target.get("bundle"))
    title = " ".join(str(target.get(k) or "") for k in ("title", "description")).strip()
    if tool in ("type", "ax_set_value") and target.get("secure"):
        return Verdict(Risk.NEVER, "a password field")
    if tool in ("type", "ax_set_value") and _CARD.search(title):
        return Verdict(Risk.NEVER, "a card number or security code field")
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
        return _button(title, apps, str(target.get("role") or ""))
    if tool == "key":
        combo = normalize_combo(str(args.get("combo", "")))
        if combo in _RISKY_COMBOS:
            reason = _RISKY_COMBOS[combo]
            if reason not in UNDO_REASONS:
                return Verdict(Risk.ASK, reason)
            # ⌘⌫ moves to the Trash in the apps that keep one, and deletes text or cells in documents. With a
            # button or nothing named in focus it may be a sheet's Delete ("keep this new document?"), and elsewhere
            # (Reminders, Calendar, Contacts, a web page, an app Milo doesn't know) it may delete for good.
            role = str(target.get("role") or "")
            if apps & set(_DOCUMENT_APPS) and role in _TEXT_ROLES + ("cell", "text"):
                return Verdict(Risk.UNDO, reason)
            if apps & set(_TRASH_APPS) and role not in ("", "button", "sheet", "dialog"):
                return Verdict(Risk.UNDO, reason)
            return Verdict(Risk.ASK, "delete")
        if combo in ("delete", "forwarddelete") and apps and str(target.get("role") or "") not in _TEXT_ROLES:
            # Delete on a selected item, not in a text field: the Trash in Mail or Photos, a cell's content in a
            # document, but a reminder, an event or a card for good.
            if apps & set(_TRASH_APPS):
                return Verdict(Risk.UNDO, "delete")
            if not apps & set(_DOCUMENT_APPS):
                return Verdict(Risk.ASK, "delete")
        if combo in _PRESS_KEYS:
            return _button(title, apps, str(target.get("role") or ""))  # return on a focused "Send" sends
        return OK
    if tool == "sheet_write":
        if target.get("new") or target.get("made") or int(target.get("filled") or 0) == 0:
            return OK  # a new document, one Milo made in this task, or empty cells
        return Verdict(Risk.ASK, "replace cells")
    if tool == "run_applescript":
        # A word list can't tell what a script does (strings can be built, apps named in variables), so
        # every script waits for a yes. Scripts about passwords never run.
        script = str(args.get("script", ""))
        if _SECRET.search(script):
            return Verdict(Risk.NEVER, "passwords")
        if _CODE.search(script):
            return Verdict(Risk.ASK, "run other programs or type for you")
        risky = _words(script)
        if risky.risk is Risk.MONEY:
            return risky
        return Verdict(Risk.ASK, risky.reason) if risky.reason else Verdict(Risk.ASK, "run a script")
    return OK


def _button(label: str, apps: set[str], role: str = "") -> Verdict:
    """A click on a button or menu item labelled `label` in one of `apps`. In a document a bare "Delete" is document
    work only as a menu item: a "Delete" button there may be the sheet that throws away a new document."""
    if apps & set(_BROWSERS):
        verdict = _words(label)
        return Verdict(Risk.ASK, "delete") if verdict.risk is Risk.UNDO else verdict
    if apps & set(_TRASH_APPS) and _TRASH_LABEL.match(label):
        return Verdict(Risk.UNDO, "delete a note" if apps & {"notes", "notizen", "com.apple.notes"} else "delete")
    if apps & set(_DOCUMENT_APPS) and _DOCUMENT_EDIT.match(label) and (
            role == "menu item" or not _BARE_DELETE.match(label)):
        return Verdict(Risk.ASK, "change the document")
    return _words(label)


def _words(text: str) -> Verdict:
    """Money anywhere in `text` wins; then anything that can't be undone; moving to the Trash alone can be."""
    found = [m.group(1).lower() for m in _RISKY.finditer(text)]
    if not found:
        return OK
    money = [w for w in found if w in _MONEY_SET]
    if money:
        return Verdict(Risk.MONEY, money[0])
    for_good = [w for w in found if w not in _TRASH_SET]
    if for_good:
        return Verdict(Risk.ASK, for_good[0])
    return Verdict(Risk.UNDO, "move to the Trash")
