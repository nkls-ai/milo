"""What Milo says and asks about routines (services/routines.py, ADR 0016).

`{computer}` is what the platform calls the machine Milo runs on ("Mac"; `Platform.computer`), so no core file names
one platform.
"""

from __future__ import annotations

WORDS: dict[str, dict[str, str]] = {
    "that_routine": {"en": "that routine", "de": "diese Routine"},
    "ask_create": {"en": "Write down how that was done as “{name}”?", "de": "Aufschreiben, wie das ging, als „{name}“?"},
    "ask_save": {"en": "Save the routine “{name}”?", "de": "Die Routine „{name}“ speichern?"},
    "ask_change": {"en": "Change the routine “{name}”?", "de": "Die Routine „{name}“ ändern?"},
    "ask_run": {"en": "Run “{name}”?", "de": "„{name}“ ausführen?"},
    "ask_schedule": {"en": "Run “{name}” {when}?", "de": "„{name}“ {when} ausführen?"},
    "ask_unschedule": {"en": "Stop running “{name}” on a schedule?", "de": "„{name}“ nicht mehr nach Plan ausführen?"},
    "ask_rename": {"en": "Rename “{name}” to “{to}”?", "de": "„{name}“ in „{to}“ umbenennen?"},
    "ask_pause": {"en": "Pause “{name}”?", "de": "„{name}“ pausieren?"},
    "ask_resume": {"en": "Resume “{name}”?", "de": "„{name}“ fortsetzen?"},
    "ask_delete": {"en": "Delete the routine “{name}”?", "de": "Die Routine „{name}“ löschen?"},
    "ask_new": {"en": "Run the new routine “{name}”?", "de": "Die neue Routine „{name}“ ausführen?"},
    "ask_changed": {"en": "“{name}” changed since you saved it. Run it?",
                    "de": "„{name}“ wurde geändert, seit du sie gespeichert hast. Trotzdem ausführen?"},
    "ask_first_scheduled": {"en": "Run “{name}” now? It's set to run {schedule}.",
                            "de": "„{name}“ jetzt ausführen? Sie ist eingestellt auf {schedule}."},
    "what_name": {"en": "What should I call it?", "de": "Wie soll ich sie nennen?"},
    "which_work": {"en": "I can't tell which work you mean. Ask me right after I've done it.",
                   "de": "Ich weiß nicht, welche Arbeit du meinst. Frag mich gleich, nachdem ich sie gemacht habe."},
    "finish_first": {"en": "Let me finish {title} first, then ask me again.",
                     "de": "Lass mich erst {title} fertig machen, dann frag mich noch mal."},
    "no_such": {"en": "I don't have a routine called {name}.", "de": "Eine Routine namens {name} habe ich nicht."},
    "no_such_that": {"en": "I don't have a routine called that.", "de": "So eine Routine habe ich nicht."},
    "what_change": {"en": "What should change in {title}?", "de": "Was soll sich an {title} ändern?"},
    "draft_broken": {"en": "I couldn't write {name} down properly: {why}. Ask me again?",
                     "de": "Ich konnte {name} nicht richtig aufschreiben: {why}. Fragst du mich noch mal?"},
    "still_writing": {"en": "I'm still writing it down. One moment.", "de": "Ich schreibe es noch auf. Einen Moment."},
    "no_draft": {"en": "There's no recipe waiting to be saved.", "de": "Es wartet kein Rezept darauf, gespeichert zu werden."},
    "unreadable": {"en": "That recipe doesn't read any more: {why}.", "de": "Das Rezept lässt sich nicht mehr lesen: {why}."},
    "saved": {"en": "Saved. Say “do {name}” whenever you want it.{when}",
              "de": "Gespeichert. Sag „mach {name}“, wann immer du sie brauchst.{when}"},
    "saved_runs": {"en": " It runs {schedule}.", "de": " Sie läuft {schedule}."},
    "what_input": {"en": "What should {input} be?", "de": "Was soll {input} sein?"},
    "then_say": {"en": "{ask} Then say “do {name}” with it.", "de": "{ask} Dann sag „mach {name}“ damit."},
    "running": {"en": "{name} is already running.", "de": "{name} läuft schon."},
    "changed_left": {"en": "{name} changed since it was saved, so I left it.",
                     "de": "{name} wurde seit dem Speichern geändert, also habe ich sie gelassen."},
    "missed_now": {"en": "I missed {name} at {time} while the {computer} was asleep, so I'm doing it now.",
                   "de": "Um {time} habe ich {name} verpasst, weil der {computer} geschlafen hat, also mache ich es "
                         "jetzt."},
    "missed": {"en": "I missed {name} on {day} at {time}, the {computer} was asleep. Say “do {name}” if you still "
                     "want it.",
               "de": "{name} am {day} um {time} habe ich verpasst, der {computer} hat geschlafen. Sag „mach {name}“, "
                     "wenn du sie noch willst."},
    "capped_one": {"en": "I skipped {name}: I've done {cap} scheduled run today, my limit for a day.",
                   "de": "{name} habe ich ausgelassen: Ich hatte heute schon {cap} geplanten Lauf, mehr mache ich an "
                         "einem Tag nicht."},
    "capped_many": {"en": "I skipped {name}: I've done {cap} scheduled runs today, my limit for a day.",
                    "de": "{name} habe ich ausgelassen: Ich hatte heute schon {cap} geplante Läufe, mehr mache ich an "
                          "einem Tag nicht."},
    "scheduled": {"en": "{name} runs {schedule} now.", "de": "{name} läuft jetzt {schedule}."},
    "unscheduled": {"en": "{name} doesn't run on its own any more.", "de": "{name} läuft nicht mehr von selbst."},
    "rename_failed": {"en": "I couldn't rename it: {why}.", "de": "Ich konnte sie nicht umbenennen: {why}."},
    "change_failed": {"en": "I couldn't change {name}: {why}.", "de": "Ich konnte {name} nicht ändern: {why}."},
    "bad_schedule": {"en": "I can't read the schedule “{schedule}”.", "de": "Den Plan „{schedule}“ kann ich nicht lesen."},
    "offer": {"en": "That's the {nth} time you've asked me for “{title}”. Want me to keep it as a routine? Say "
                    "“remember how to do this” and give it a name.",
              "de": "Das ist das {nth} Mal, dass du mich um „{title}“ bittest. Soll ich es mir als Routine merken? Sag "
                    "„merk dir, wie das geht“ und gib ihr einen Namen."},
    "nth.3": {"en": "third", "de": "dritte"},
    "nth.4": {"en": "fourth", "de": "vierte"},
    "nth.5": {"en": "fifth", "de": "fünfte"},
    "nth": {"en": "{n}th", "de": "{n}."},
}
