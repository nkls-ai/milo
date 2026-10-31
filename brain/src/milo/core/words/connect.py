"""What Milo asks before one of his connection tools when its action level is ask_first (core/wording.py).

English only for now: the worker's tools ask through the tool socket, which doesn't know the user's language yet.
"""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "calendar_add_event": {"en": "Put {title} in your calendar on {when}?"},
    "reminders_add": {"en": "Add the reminder {title}{due}?"},
    "reminders_due": {"en": " for {when}"},
    "reminders_complete": {"en": "Tick off that reminder?"},
    "mail_draft": {"en": "Write a draft to {everyone}? It stays in Mail until you send it."},
    "mail_reply_draft": {"en": "Write a reply draft? It stays in Mail until you send it."},
    "mail_forward": {"en": "Pass on {what} to {everyone}, with anything attached? It stays in Mail until you send it."},
    "mail_forward_email": {"en": "{sender}'s email {subject}"},
    "mail_forward_that": {"en": "that email"},
    "notes_create": {"en": "Make a new note called {title}?"},
    "notes_append": {"en": "Add this to your note?"},
    "files_move": {"en": "Move {what} into {folder}?"},
    "shortcuts_run": {"en": "I'm about to run your shortcut {name}{given}. Go ahead?"},
    "shortcuts_input": {"en": " with {input}"},
    "install_package": {"en": "Install “{package}” with {manager}?"},
    "other": {"en": "{title}?"},
    "go_ahead": {"en": "Go ahead"},
}
