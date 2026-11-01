// The words on a done card apart from its title (DoneCardText in DoneCards.swift).
//
// The title and the detail come from the brain, in the language Milo answered in. The card's own words follow that
// language (action_done's `lang`), so a German line never sits above an English card; when the brain names none, they
// follow the system's. English and German, like Milo's spoken lines; any other language gets English.
import * as Format from "format.mjs"

const german = {
    "In your calendar": "In deinem Kalender", "In %@": "In %@", "On your list": "Auf deiner Liste",
    "I'll remind you": "Ich erinnere dich", "In your notes": "In deinen Notizen", "Timer running": "Timer läuft",
    "Draft, not sent": "Entwurf, nicht gesendet", "Shortcut ran": "Kurzbefehl ausgeführt", "Music": "Musik",
    "Opened": "Geöffnet", "Done": "Erledigt", "Rings at %@": "Klingelt um %@", "Today": "Heute",
    "Tomorrow": "Morgen", "Calendar": "Kalender", "To-do": "To-do", "Reminder": "Erinnerung",
    "Note written": "Notiz geschrieben", "Timer": "Timer", "Draft written": "Entwurf geschrieben",
    "Shows your reminders in the Milo window": "Zeigt deine Erinnerungen im Milo-Fenster",
    "Shows it": "Zeigt es", "Opens it": "Öffnet es", "Opens it in %@": "Öffnet es in %@",
    "Ready to copy": "Bereit zum Kopieren", "Written": "Geschrieben", "Written, ready to copy": "Geschrieben, bereit zum Kopieren",
    "On your clipboard": "In der Zwischenablage", "Copied": "Kopiert",
    "Alarm set": "Wecker gestellt", "Alarm": "Wecker",
    "Shows it in the Milo window, to copy": "Zeigt es im Milo-Fenster, zum Kopieren",
    "Sent": "Gesendet", "Called": "Angerufen", "Message sent": "Nachricht gesendet", "Call": "Anruf",
    "Sound": "Ton", "Screen": "Bildschirm",
}

// The card's words, looked up by their English text ("%@" takes the one argument), and the locale its dates use.
export function words(action) {
    const system = Qt.locale().name.split("_")[0]
    const code = (action.lang || system) === "de" ? "de" : "en"
    const w = (english, argument) => (code === "de" ? german[english] || english : english).replace("%@", argument || "")
    const locale = !action.lang || code === system ? Qt.locale() : Qt.locale(code === "de" ? "de_DE" : "en_GB")
    return { w: w, locale: locale }
}

function hour(date, locale) { return date.toLocaleTimeString(locale, locale.timeFormat(1)) }

// "Today 15:00", "Tomorrow 09:00", "Thu 5 Nov, 15:00"; a timer says when it rings, and an event only its time,
// since its calendar page shows the day.
export function when(kind, date, now, w, locale) {
    const h = hour(date, locale)
    if (kind === "timer") return w("Rings at %@", h)
    if (kind === "event") return h
    if (Format.sameDay(date, now)) return w("Today") + " " + h
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    if (Format.sameDay(date, tomorrow)) return w("Tomorrow") + " " + h
    return date.toLocaleDateString(locale, "ddd d MMM") + ", " + h
}

// The line under the title: when it is, and the detail; or where it went when it has neither.
export function line(action, now) {
    const { w, locale } = words(action)
    const date = Format.parse(action.when)
    const parts = [date ? when(action.kind, date, now, w, locale) : "", action.detail || ""].filter(p => p)
    if (parts.length) return parts.join(", ")
    const inApp = fallback => action.app ? w("In %@", action.app) : w(fallback)
    switch (action.kind) {
    case "event": return inApp("In your calendar")
    case "todo": return inApp("On your list")
    case "reminder": return w("I'll remind you")
    case "note": return inApp("In your notes")
    case "timer": return w("Timer running")
    case "alarm": return w("Alarm set")
    case "draft": return w("Draft, not sent")
    case "shortcut": return w("Shortcut ran")
    // The title says what happened ("Paused"); the player, if it said which one it is.
    case "music": return action.app || w("Music")
    case "opened": return inApp("Opened")
    case "written": return inApp("Ready to copy")
    case "copied": return w("On your clipboard")
    case "message": return w("Sent")
    case "call": return w("Called")
    case "sound": return w("Sound")
    case "brightness": return w("Screen")
    default: return w("Done")
    }
}

const kinds = { event: "Calendar", todo: "To-do", reminder: "Reminder", note: "Note written", timer: "Timer",
                alarm: "Alarm", draft: "Draft written", shortcut: "Shortcut ran", music: "Music", opened: "Opened",
                copied: "Copied", message: "Message sent", call: "Call", sound: "Sound", brightness: "Screen" }

// What a screen reader says for the card.
export function spoken(action, now) {
    const { w, locale } = words(action)
    const what = action.kind === "written" ? w(action.app ? "Written" : "Written, ready to copy") : w(kinds[action.kind] || "Done")
    let said = what + ": " + action.title + ", " + line(action, now)
    const date = Format.parse(action.when)
    if (action.kind === "event" && date) said += ", " + date.toLocaleDateString(locale, "dddd d MMMM")
    return said
}

// What a click on the card does, for the tooltip and screen readers.
export function opens(action) {
    const { w } = words(action)
    if (action.kind === "reminder" && !action.app) return w("Shows your reminders in the Milo window")
    if (action.kind === "opened") return w("Shows it")
    if ((action.kind === "written" && !action.app) || action.kind === "copied") return w("Shows it in the Milo window, to copy")
    return action.app ? w("Opens it in %@", action.app) : w("Opens it")
}
