"""What Milo asks before the worker's risky step on the screen, and before he borrows the mouse or keyboard
(services/hands.py)."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "open_url": {"en": "Open {host}{in_app}?", "de": "{host}{in_app} öffnen?"},
    "use": {"en": "May I use {app} for this? You'll see each step.",
            "de": "Darf ich dafür {app} benutzen? Du siehst jeden Schritt."},
    "that_app": {"en": "that app", "de": "diese App"},
    "click": {"en": "I'm about to click “{what}”{in_app}. Go ahead?", "de": "Ich klicke gleich auf „{what}“{in_app}. Okay?"},
    "type": {"en": "I'm about to type “{text}”{in_app}, which may {reason}. Go ahead?",
             "de": "Ich tippe gleich „{text}“{in_app}. Das kann {reason}. Okay?"},
    "key": {"en": "I'm about to press {combo}{in_app}, which may {reason}. Go ahead?",
            "de": "Ich drücke gleich {combo}{in_app}. Das kann {reason}. Okay?"},
    "script": {"en": "May I work {where}?{could} You can read the steps in my window.",
               "de": "Darf ich {where} arbeiten?{could} Die Schritte stehen in meinem Fenster."},
    "script_in": {"en": "in {apps} directly", "de": "direkt in {apps}"},
    "script_anywhere": {"en": "in your apps directly", "de": "direkt in deinen Apps"},
    "script_could": {"en": " It could {reason}.", "de": " Das könnte {reason}."},
    "sheet_one": {"en": "Replace {n} filled cell in “{doc}”?", "de": "{n} gefüllte Zelle in „{doc}“ ersetzen?"},
    "sheet_many": {"en": "Replace {n} filled cells in “{doc}”?", "de": "{n} gefüllte Zellen in „{doc}“ ersetzen?"},
    "front_document": {"en": "the front document", "de": "dem vorderen Dokument"},
    "other": {"en": "I'm about to {reason}{in_app}. Go ahead?", "de": "Darf ich{in_app} {reason}?"},
    "unknown_reason": {"en": "{reason}", "de": "„{reason}“ auslösen"},
    "borrow": {"en": "Can I borrow your {device} for a moment, to {verb}{in_app}?",
               "de": "Darf ich mir kurz {device} leihen, um{in_app} {verb}?"},
    "device.mouse": {"en": "mouse", "de": "deine Maus"},
    "device.keyboard": {"en": "keyboard", "de": "deine Tastatur"},
    "borrow.click": {"en": "click", "de": "zu klicken"},
    "borrow.type": {"en": "type", "de": "zu tippen"},
    "borrow.key": {"en": "press a key", "de": "eine Taste zu drücken"},
    "borrow.scroll": {"en": "scroll", "de": "zu scrollen"},
    "borrow.other": {"en": "do this", "de": "das zu machen"},
}

REASONS_DE: dict[str, str] = {
    "send": "etwas senden", "send now": "etwas senden", "submit": "etwas absenden", "publish": "etwas veröffentlichen",
    "post": "etwas posten", "share": "etwas teilen", "confirm": "etwas bestätigen", "delete": "etwas löschen",
    "remove": "etwas entfernen", "trash": "etwas löschen", "erase": "etwas löschen", "delete a note": "eine Notiz löschen",
    "move to the Trash": "etwas in den Papierkorb legen", "empty the Trash": "den Papierkorb leeren",
    "delete it for good": "etwas endgültig löschen", "delete immediately": "etwas endgültig löschen",
    "delete permanently": "etwas endgültig löschen", "don't save": "Änderungen verwerfen",
    "don’t save": "Änderungen verwerfen", "discard": "Änderungen verwerfen", "overwrite": "etwas überschreiben",
    "replace": "etwas ersetzen", "replace cells": "Zellen ersetzen", "change the document": "das Dokument ändern",
    "change a system setting": "eine Systemeinstellung ändern",
    "click something I can't name": "auf etwas klicken, das ich nicht benennen kann",
    "open a program that runs commands": "ein Programm öffnen, das Befehle ausführt", "run a command": "einen Befehl ausführen",
    "run a script": "ein Skript ausführen", "run other programs or type for you": "andere Programme starten oder für dich tippen",
    "uninstall": "etwas deinstallieren", "unsubscribe": "etwas abbestellen", "buy": "etwas kaufen", "buy now": "etwas kaufen",
    "purchase": "etwas kaufen", "pay": "bezahlen", "pay now": "bezahlen", "checkout": "bezahlen", "check out": "bezahlen",
    "order": "etwas bestellen", "place order": "etwas bestellen", "transfer": "Geld überweisen", "sell": "etwas verkaufen",
    "withdraw": "Geld abheben", "cancel subscription": "ein Abo kündigen", "close account": "ein Konto schließen",
    "delete account": "ein Konto löschen",
}
"""Risk reasons (services/risk.py) as German phrases for a question; English says the reason as it is. A reason
missing here is quoted ("unknown_reason")."""
