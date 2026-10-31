"""The line after a <write> (services/writing.py, ADR 0033): "pasted", or why it is only in the window (the app's
`why`)."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "pasted": {"en": "It's in {app}, have a look.", "de": "Steht in {app}, schau mal drüber."},
    "pasted_here": {"en": "It's in, have a look.", "de": "Steht drin, schau mal drüber."},
    "copy_failed": {"en": "I couldn't reach the clipboard, so it's in my window to copy.",
                    "de": "An die Zwischenablage kam ich nicht ran. Es liegt zum Kopieren in meinem Fenster."},
    "here": {"en": "Here it is, ready to copy.", "de": "Hier ist es, zum Kopieren."},
    "moved": {
        "en": "You'd moved on, so I didn't paste it. It's in my window to copy.",
        "de": "Du warst schon woanders, also hab ich's nicht eingefügt. Es liegt zum Kopieren in meinem Fenster.",
    },
    "no_field": {
        "en": "I didn't find a text field there, so it's in my window to copy.",
        "de": "Ich hab dort kein Textfeld gefunden. Es liegt zum Kopieren in meinem Fenster.",
    },
    "terminal": {
        "en": "I don't paste into a terminal, so it's in my window to copy.",
        "de": "In ein Terminal füge ich nichts ein. Es liegt zum Kopieren in meinem Fenster.",
    },
    "secure": {
        "en": "That's a password field, so I didn't paste. It's in my window to copy.",
        "de": "Das ist ein Passwortfeld, da füge ich nichts ein. Es liegt zum Kopieren in meinem Fenster.",
    },
    "outside": {
        "en": "This comes from something I read, so look it over first. It's in my window to copy.",
        "de": "Das stammt aus etwas, das ich gelesen habe, schau es erst durch. Es liegt zum Kopieren in meinem Fenster.",
    },
    "failed": {
        "en": "I couldn't paste it, so it's in my window to copy.",
        "de": "Ich konnte es nicht einfügen. Es liegt zum Kopieren in meinem Fenster.",
    },
}
