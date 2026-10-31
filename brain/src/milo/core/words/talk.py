"""What Milo asks before he acts on a tag of the talker's reply that needs a yes (services/live_talk.py)."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "start_titled": {"en": "Start “{title}”?", "de": "„{title}“ starten?"},
    "go_ahead": {"en": "Go ahead", "de": "Loslegen"},
    "steer": {"en": "Change the task to {change}", "de": "Aufgabe ändern: {change}"},
    "open": {"en": "Open {what}?", "de": "{what} öffnen?"},
    "remember": {"en": "Should I remember this: {fact}?", "de": "Soll ich mir das merken: {fact}?"},
    "remind": {"en": "Should I remind you on {when}: {what}?", "de": "Soll ich dich am {when} erinnern: {what}?"},
}
