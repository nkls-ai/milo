"""The one spoken line about a voice task still at work (services/updates.py, ADR 0032), by the kind of work."""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "open": {
        "en": "Opening {app} now…",
        "de": "Ich öffne gerade {app}…",
        "fr": "J'ouvre {app}…",
        "es": "Abriendo {app}…",
    },
    "working": {
        "en": "Working in {app} now…",
        "de": "Ich bin gerade in {app}…",
        "fr": "Je travaille dans {app}…",
        "es": "Trabajando en {app}…",
    },
    "calendar": {
        "en": "Checking your calendar…",
        "de": "Ich schaue in deinen Kalender…",
        "fr": "Je regarde ton agenda…",
        "es": "Mirando tu calendario…",
    },
    "mail": {
        "en": "Going through your mail…",
        "de": "Ich gehe deine Mails durch…",
        "fr": "Je parcours tes mails…",
        "es": "Revisando tu correo…",
    },
    "reminders": {
        "en": "Looking at your reminders…",
        "de": "Ich schaue in deine Erinnerungen…",
        "fr": "Je regarde tes rappels…",
        "es": "Mirando tus recordatorios…",
    },
    "notes": {
        "en": "Looking in your notes…",
        "de": "Ich schaue in deine Notizen…",
        "fr": "Je regarde tes notes…",
        "es": "Mirando tus notas…",
    },
    "files": {
        "en": "Looking through your files…",
        "de": "Ich suche in deinen Dateien…",
        "fr": "Je cherche dans tes fichiers…",
        "es": "Buscando en tus archivos…",
    },
    "web": {
        "en": "Looking it up online…",
        "de": "Ich schaue online nach…",
        "fr": "Je cherche en ligne…",
        "es": "Buscándolo en internet…",
    },
    "edit": {
        "en": "Making the changes now…",
        "de": "Ich mache gerade die Änderungen…",
        "fr": "Je fais les changements…",
        "es": "Haciendo los cambios…",
    },
    "still": {"en": "Still on it…", "de": "Bin noch dran…", "fr": "J'y suis encore…", "es": "Sigo en ello…"},
}
