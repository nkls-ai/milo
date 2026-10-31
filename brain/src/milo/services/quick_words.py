"""The one line Milo says after a quick action is done (ADR 0029), in the user's language.

Milo says it himself, from a template, once the action really happened: the live model doesn't promise it before.
English and German for now; another language falls back to English. The language is the one of the message being
answered (`SpokenLanguage`, ADR 0028), the same one the reply and Milo's other questions follow.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

LANGS = ("en", "de")
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

_DAYS = {"en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
         "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")}
_MONTHS = {"en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                  "November", "December"),
           "de": ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
                  "November", "Dezember")}
_NEAR = {"en": ("today", "tomorrow", "the day after tomorrow"), "de": ("heute", "morgen", "übermorgen")}


def language(code: str) -> str:
    """The language of the message being answered, if Milo has lines in it, else English."""
    return code if code in LANGS else "en"


def line(key: str, lang: str, **values: str) -> str:
    templates = LINES[key]
    return templates.get(lang, templates["en"]).format(**values)


def ask(key: str, lang: str, **values: str) -> str:
    templates = QUESTIONS[key]
    return templates.get(lang, templates["en"]).format(**values)


def day(d: date, today: date, lang: str) -> str:
    """"today", "tomorrow", "Thursday" within a week, else "Thursday 12 November"."""
    lang = lang if lang in LANGS else "en"
    ahead = (d - today).days
    if 0 <= ahead < 3:
        return _NEAR[lang][ahead]
    name = _DAYS[lang][d.weekday()]
    if 0 < ahead < 7:
        return name
    return f"{name}, {d.day}. {_MONTHS[lang][d.month - 1]}" if lang == "de" else \
        f"{name} {d.day} {_MONTHS[lang][d.month - 1]}"


def clock(t: datetime, lang: str) -> str:
    """"at 3 pm", "at 3:30 pm"; "um 15 Uhr", "um 15:30"."""
    if lang == "de":
        return f"um {t.hour} Uhr" if t.minute == 0 else f"um {t:%H:%M}"
    hour = t.hour % 12 or 12
    half = "am" if t.hour < 12 else "pm"
    return f"at {hour} {half}" if t.minute == 0 else f"at {hour}:{t:%M} {half}"


def when(t: datetime, today: date, lang: str, *, all_day: bool = False) -> str:
    """"Thursday at 3 pm", "morgen um 9 Uhr"; a whole day says only the day."""
    d = day(t.date(), today, lang)
    return d if all_day else f"{d} {clock(t, lang)}"


def span(seconds: float, lang: str) -> str:
    """"10 minutes", "1 hour 30 minutes", "90 seconds"; "10 Minuten"."""
    seconds = max(1, round(seconds))
    words = {"en": (("hour", "hours"), ("minute", "minutes"), ("second", "seconds")),
             "de": (("Stunde", "Stunden"), ("Minute", "Minuten"), ("Sekunde", "Sekunden"))}[lang if lang in LANGS
                                                                                            else "en"]
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if seconds < 120 and not hours:
        minutes, secs = (0, seconds) if seconds % 60 else (seconds // 60, 0)
    parts = [(n, w) for n, w in zip((hours, minutes, secs), words) if n]
    return " ".join(f"{n} {w[0] if n == 1 else w[1]}" for n, w in parts) or f"0 {words[2][1]}"


def end_of(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), datetime.min.time())
