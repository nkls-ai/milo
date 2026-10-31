"""What Milo says when he takes back what a task did (services/undo.py, ADR 0026)."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "too_old": {"en": "I can't undo that any more: I keep what I need to undo a task for a day.",
                "de": "Das kann ich nicht mehr rückgängig machen: Was ich dafür brauche, behalte ich einen Tag lang."},
    "nothing": {"en": "There's nothing of mine to undo right now.",
                "de": "Gerade gibt es nichts von mir, was ich rückgängig machen könnte."},
    "that_task": {"en": "that task", "de": "diese Aufgabe"},
    "the_task": {"en": "the task", "de": "die Aufgabe"},
    "quote": {"en": "“{text}”", "de": "„{text}“"},
    "and": {"en": "{names} and {last}", "de": "{names} und {last}"},
    "already": {"en": "“{title}” is already undone.", "de": "„{title}“ ist schon rückgängig gemacht."},
    "went_wrong": {"en": "Something went wrong while I undid “{title}”.",
                   "de": "Beim Rückgängigmachen von „{title}“ ist etwas schiefgegangen."},
    "changed_one": {"en": "{names} changed since “{title}”. Undo anyway? Your changes since would be lost.",
                    "de": "{names} wurde seit „{title}“ geändert. Trotzdem rückgängig machen? Deine Änderungen seitdem "
                          "gehen dann verloren."},
    "changed_many": {"en": "{names} changed since “{title}”. Undo anyway? Your changes since would be lost.",
                     "de": "{names} wurden seit „{title}“ geändert. Trotzdem rückgängig machen? Deine Änderungen "
                           "seitdem gehen dann verloren."},
    "left_one": {"en": "Okay, I left {names} as it is.", "de": "Okay, ich lasse {names}, wie es ist."},
    "left_many": {"en": "Okay, I left {names} as they are.", "de": "Okay, ich lasse {names}, wie sie sind."},
    "back_one": {"en": "Undid “{title}”: {names} is back the way it was.",
                 "de": "„{title}“ ist rückgängig gemacht: {names} ist wieder wie vorher."},
    "back_many": {"en": "Undid “{title}”: {names} are back the way they were.",
                  "de": "„{title}“ ist rückgängig gemacht: {names} sind wieder wie vorher."},
    "not_back": {"en": "I couldn't put {names} back.", "de": "{names} konnte ich nicht zurückholen."},
    "helper_rest": {"en": "A helper is putting back the rest.", "de": "Den Rest stellt ein Helfer wieder her."},
    "helper_all": {"en": "I'm undoing “{title}”: a helper is putting things back.",
                   "de": "Ich mache „{title}“ rückgängig: Ein Helfer stellt alles wieder her."},
    "only_opened": {"en": "Nothing to undo for “{title}”: it only opened windows or tabs. Close them if you don't "
                          "need them.",
                    "de": "Bei „{title}“ gibt es nichts rückgängig zu machen: Es hat nur Fenster oder Tabs geöffnet. "
                          "Schließ sie, wenn du sie nicht brauchst."},
    "no_change": {"en": "Nothing to undo for “{title}”: it didn't change anything.",
                  "de": "Bei „{title}“ gibt es nichts rückgängig zu machen: Es hat nichts geändert."},
    "cant_now": {"en": "I can't undo “{title}” right now.", "de": "„{title}“ kann ich gerade nicht rückgängig machen."},
    "failed": {"en": "I couldn't undo “{title}”: {why}.", "de": "Ich konnte „{title}“ nicht rückgängig machen: {why}."},
    "did_not_work": {"en": "it did not work", "de": "es hat nicht geklappt"},
    "left_it": {"en": "Okay, I left “{title}” as it is.", "de": "Okay, ich lasse „{title}“, wie es ist."},
    "undid": {"en": "Undid “{title}”.", "de": "„{title}“ ist rückgängig gemacht."},
    "helper_task": {"en": "Undo “{title}”", "de": "„{title}“ rückgängig machen"},
    "helper_title": {"en": "Undo: {title}", "de": "Rückgängig: {title}"},
}
