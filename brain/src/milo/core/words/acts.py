"""What Milo says after a quick action (ADR 0029), and what he asks before one that needs a yes.

Milo says a line himself, from a template, once the action really happened: the live model doesn't promise it
before.
"""

from __future__ import annotations

LINES: dict[str, dict[str, str]] = {
    "event": {"en": "{title}, {when}. It's in.", "de": "{title}, {when}. Steht drin."},
    "moved": {"en": "Moved {title} to {when}.", "de": "{title} ist jetzt {when}."},
    "cancelled": {"en": "{title} is off your calendar.", "de": "{title} ist aus dem Kalender raus."},
    "todo": {"en": "{title}. It's on your list.", "de": "{title}. Steht auf der Liste."},
    "todo_due": {"en": "{title}, {when}. It's on your list.", "de": "{title}, {when}. Steht auf der Liste."},
    "note": {"en": "Noted: {title}.", "de": "Notiert: {title}."},
    "timer": {"en": "Timer for {span} is running.", "de": "Timer läuft, {span}."},
    "timer_named": {"en": "{title}: {span} timer is running.", "de": "{title}: Timer läuft, {span}."},
    "ring": {"en": "Time's up!", "de": "Die Zeit ist um!"},
    "ring_named": {"en": "Time's up: {title}.", "de": "Die Zeit ist um: {title}."},
    "draft": {"en": "The draft is open in Mail.", "de": "Der Entwurf ist offen in Mail."},
    "draft_to": {"en": "The draft to {who} is open in Mail.", "de": "Der Entwurf an {who} ist offen in Mail."},
    "shortcut": {"en": "Done: {title}.", "de": "Erledigt: {title}."},
    "play": {"en": "Playing.", "de": "Läuft."},
    "pause": {"en": "Paused.", "de": "Pausiert."},
    "next": {"en": "Next one.", "de": "Nächster."},
    "previous": {"en": "Back one.", "de": "Einer zurück."},
    "meeting_start": {"en": "I'm taking notes.", "de": "Ich schreibe mit."},
    "meeting_stop": {"en": "I've stopped taking notes. They'll be ready in a moment.",
                     "de": "Ich schreibe nicht mehr mit. Die Notizen kommen gleich."},
    "meeting_pause": {"en": "Notes paused.", "de": "Notizen pausiert."},
    "meeting_resume": {"en": "Taking notes again.", "de": "Ich schreibe wieder mit."},
    "meeting_none": {"en": "I'm not taking notes right now.", "de": "Ich schreibe gerade nicht mit."},
    "failed": {"en": "That didn't work: {why}", "de": "Das hat nicht geklappt: {why}"},
    "declined": {"en": "Okay, I left it.", "de": "Okay, ich lasse es."},
}

QUESTIONS: dict[str, dict[str, str]] = {
    "event": {"en": "Add “{title}” to your calendar, {when}?", "de": "„{title}“ eintragen, {when}?"},
    "move": {"en": "Move “{title}” to {when}?", "de": "„{title}“ auf {when} verschieben?"},
    "cancel": {"en": "Delete “{title}”, {when}, from your calendar?",
               "de": "„{title}“, {when}, aus dem Kalender löschen?"},
    "invite": {"en": " It's an invite, so the others will see it.",
               "de": " Es ist eine Einladung, die anderen sehen das."},
    "series": {"en": " It repeats; only this one goes.", "de": " Er wiederholt sich, nur dieser fällt weg."},
    "todo": {"en": "Add “{title}” to your Reminders?", "de": "„{title}“ zu deinen Erinnerungen hinzufügen?"},
    "note": {"en": "Make a note: “{title}”?", "de": "Notiz anlegen: „{title}“?"},
    "draft": {"en": "Write a mail draft to {who}?", "de": "Einen Mail-Entwurf an {who} schreiben?"},
    "shortcut": {"en": "Run the shortcut “{title}”?", "de": "Den Kurzbefehl „{title}“ ausführen?"},
    "play": {"en": "Play the music?", "de": "Musik abspielen?"},
    "pause": {"en": "Pause the music?", "de": "Musik pausieren?"},
    "next": {"en": "Skip to the next song?", "de": "Zum nächsten Titel?"},
    "previous": {"en": "Go back a song?", "de": "Einen Titel zurück?"},
    "meeting_start": {"en": "Take notes of this meeting?", "de": "Bei diesem Meeting mitschreiben?"},
    "meeting_resume": {"en": "Take notes again?", "de": "Wieder mitschreiben?"},
    "event_changed": {"en": "“{title}” changed since. Undo anyway? Your changes since would be lost.",
                      "de": "„{title}“ wurde seitdem geändert. Trotzdem rückgängig machen? Deine Änderungen gehen "
                            "dann verloren."},
    "note_changed": {"en": "The note “{title}” changed since. Delete it anyway? It goes to Recently Deleted.",
                     "de": "Die Notiz „{title}“ wurde seitdem geändert. Trotzdem löschen? Sie kommt in „Zuletzt "
                           "gelöscht“."},
}
"""What Milo asks before an act that needs a yes, and before an Undo of something changed since."""
