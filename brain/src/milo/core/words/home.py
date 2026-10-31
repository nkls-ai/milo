"""What Milo says after switching something at home or a Focus (ADR 0037), and what he asks before a lock, a garage
door or the alarm.

"{title}: on." rather than "{title} is on.": the title can be one lamp or all the kitchen lights.
"""

from __future__ import annotations

LINES: dict[str, dict[str, str]] = {
    "on": {"en": "{title}: on.", "de": "{title}: an."},
    "off": {"en": "{title}: off.", "de": "{title}: aus."},
    "toggle": {"en": "{title}: switched.", "de": "{title}: umgeschaltet."},
    "percent": {"en": "{title}: {value} percent.", "de": "{title}: {value} Prozent."},
    "degrees": {"en": "{title}: {value} degrees.", "de": "{title}: {value} Grad."},
    "run": {"en": "Scene on: {title}.", "de": "Szene an: {title}."},
    "open": {"en": "{title}: open.", "de": "{title}: offen."},
    "close": {"en": "{title}: closed.", "de": "{title}: zu."},
    "lock": {"en": "{title}: locked.", "de": "{title}: abgeschlossen."},
    "unlock": {"en": "{title}: unlocked.", "de": "{title}: aufgeschlossen."},
    "arm": {"en": "{title}: armed.", "de": "{title}: scharf."},
    "disarm": {"en": "{title}: disarmed.", "de": "{title}: unscharf."},
    "which": {"en": "Which one: {names}?", "de": "Welches: {names}?"},
    "none": {"en": "No home is connected yet. I work with Home Assistant: add its address to config.toml and its "
                   "token to my secrets folder.",
             "de": "Noch ist kein Zuhause verbunden. Ich kann mit Home Assistant: trag die Adresse in config.toml "
                   "ein und den Token in meinen secrets-Ordner."},
    "setup_shortcuts": {"en": "I don't see your home yet. Make a shortcut for each scene or device you want, like "
                              "“Living room lights on”, and put them in a Shortcuts folder called “Milo Home”.",
                        "de": "Ich sehe dein Zuhause noch nicht. Leg für jede Szene oder jedes Gerät einen Kurzbefehl "
                              "an, etwa „Wohnzimmer Licht an“, in einem Ordner „Milo Home“ in Kurzbefehle."},
    "setup_home_assistant": {"en": "Home Assistant shows me no lights, switches or scenes yet.",
                             "de": "Home Assistant zeigt mir noch keine Lichter, Schalter oder Szenen."},
    "why_not_found": {"en": "I couldn't find “{title}” at home", "de": "ich habe „{title}“ zu Hause nicht gefunden"},
    "why_cant": {"en": "“{title}” can't do that", "de": "„{title}“ kann das nicht"},
    "why_no_value": {"en": "say how much, like 50 percent or 21 degrees",
                     "de": "sag wie viel, etwa 50 Prozent oder 21 Grad"},
    "dnd": {"en": "Do Not Disturb", "de": "Nicht stören"},
    "focus_on": {"en": "{title} is on.", "de": "{title} ist an."},
    "focus_off": {"en": "{title} is off.", "de": "{title} ist aus."},
    "focus_none": {"en": "I can't switch Focus on this computer yet.",
                   "de": "Fokus kann ich auf diesem Computer noch nicht umschalten."},
    "focus_setup": {"en": "To switch {title} I need two small shortcuts. I've opened them: click Add Shortcut on "
                          "each, then ask me again.",
                    "de": "Für {title} brauche ich zwei kleine Kurzbefehle. Ich habe sie geöffnet: klick bei beiden "
                          "auf „Kurzbefehl hinzufügen“, dann frag mich noch mal."},
    "focus_make": {"en": "To switch {title} I need your shortcuts for it: make one called “{title} on” with the Set "
                         "Focus action, and one called “{title} off”.",
                   "de": "Für {title} brauche ich Kurzbefehle: leg einen namens „{title} an“ mit der Aktion „Fokus "
                         "festlegen“ an, und einen namens „{title} aus“."},
}

QUESTIONS: dict[str, dict[str, str]] = {
    "on": {"en": "Turn on “{title}”?", "de": "„{title}“ einschalten?"},
    "off": {"en": "Turn off “{title}”?", "de": "„{title}“ ausschalten?"},
    "toggle": {"en": "Switch “{title}”?", "de": "„{title}“ umschalten?"},
    "set": {"en": "Set “{title}” to {value}?", "de": "„{title}“ auf {value} stellen?"},
    "run": {"en": "Start the scene “{title}”?", "de": "Die Szene „{title}“ starten?"},
    "open": {"en": "Open “{title}”?", "de": "„{title}“ öffnen?"},
    "close": {"en": "Close “{title}”?", "de": "„{title}“ schließen?"},
    "lock": {"en": "Lock “{title}”?", "de": "„{title}“ abschließen?"},
    "unlock": {"en": "Unlock “{title}”?", "de": "„{title}“ aufschließen?"},
    "arm": {"en": "Arm “{title}”?", "de": "„{title}“ scharf schalten?"},
    "disarm": {"en": "Disarm “{title}”?", "de": "„{title}“ unscharf schalten?"},
}
"""What Milo asks before a lock, a garage door or the alarm (every time), and before anything else at home after
outside text in the stricter modes."""
