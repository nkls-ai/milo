// Routines in words (RoutineViews.swift, Wire/Routine.swift): a routine's line, when it runs next, and a recipe
// draft read for a person.
import * as Format from "format.mjs"

// "Every Monday at 09:00 · last run Oct 26, 09:00, done", "Every …, paused", "Only when you ask", or its problem.
export function summary(routine) {
    if (routine.problem) return routine.problem
    const parts = []
    if (!routine.schedule) parts.push("Only when you ask")
    else parts.push(routine.schedule.charAt(0).toUpperCase() + routine.schedule.slice(1) + (routine.paused ? ", paused" : ""))
    if (routine.last_run) parts.push("last run " + lastRun(routine.last_run))
    return parts.join(" · ")
}

// "2026-10-26 09:00, done" as "26 Oct, 09:00, done"; anything else as it is.
export function lastRun(text) {
    const comma = text.indexOf(",")
    const head = comma < 0 ? text : text.slice(0, comma)
    const date = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(head.trim()) ? Format.parse(head.trim()) : null
    if (!date) return text
    const when = Qt.formatDate(date, "d MMM") + ", " + Format.time(date)
    return comma < 0 ? when : when + ", " + text.slice(comma + 1).trim()
}

// The routine whose schedule comes up first; null if none.
export function nextUp(routines) {
    let best = null
    for (const r of routines || []) {
        if (r.problem || r.paused || !r.next_run) continue
        if (!best || r.next_run < best.next_run) best = r
    }
    return best
}

// "today at 09:00", "tomorrow at 09:00", "Monday at 09:00", "on 2 Nov at 09:00".
export function when(date, now) {
    const time = Format.time(date)
    if (Format.sameDay(date, now)) return "today at " + time
    const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    if (Format.sameDay(date, tomorrow)) return "tomorrow at " + time
    const days = Math.round((new Date(date.getFullYear(), date.getMonth(), date.getDate())
                             - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000)
    if (days < 7) return Qt.formatDate(date, "dddd") + " at " + time
    return "on " + Qt.formatDate(date, "d MMM") + " at " + time
}

function frontMatter(recipe) {
    const lines = String(recipe || "").split("\n")
    if (lines[0].trim() !== "---") return []
    const end = lines.slice(1).findIndex(l => l.trim() === "---")
    return end < 0 ? [] : lines.slice(1, end + 1)
}

function value(text) {
    const t = text.trim()
    if (t.length >= 2 && t.startsWith('"') && t.endsWith('"')) {
        try { return JSON.parse(t) } catch (e) { return t }
    }
    return t
}

// The recipe without its front matter: what a person reads to check it.
export function steps(recipe) {
    const lines = String(recipe || "").split("\n")
    if (lines[0].trim() !== "---") return String(recipe || "").trim()
    const end = lines.slice(1).findIndex(l => l.trim() === "---")
    return end < 0 ? String(recipe).trim() : lines.slice(end + 2).join("\n").trim()
}

// The front matter's inputs as "month: Which month? (usually last month)".
export function inputs(recipe) {
    const out = []
    let current = null
    let inInputs = false
    const flush = () => {
        if (current) out.push(current.name + (current.ask ? ": " + current.ask : "") + (current.fallback ? " (usually " + current.fallback + ")" : ""))
        current = null
    }
    for (const line of frontMatter(recipe)) {
        if (!line.startsWith(" ")) { flush(); inInputs = line.startsWith("inputs:"); continue }
        if (!inInputs) continue
        const text = line.trim()
        if (text.startsWith("- name:")) { flush(); current = { name: value(text.slice(7)), ask: "", fallback: "" } }
        else if (text.startsWith("ask:") && current) current.ask = value(text.slice(4))
        else if (text.startsWith("default:") && current) current.fallback = value(text.slice(8))
    }
    flush()
    return out
}

// The front matter's apps line, "[Finder, Numbers]": a run with apps uses the screen.
export function apps(recipe) {
    for (const line of frontMatter(recipe)) {
        if (!line.startsWith("apps:")) continue
        return line.slice(5).trim().replace(/^\[|\]$/g, "").split(",").map(value).filter(a => a)
    }
    return []
}

// The steps' lines for reading: "## Steps" becomes a heading, blank lines go, indented lines stay indented.
export function lines(text) {
    return String(text || "").split("\n").map(line => {
        const trimmed = line.trim()
        if (!trimmed) return null
        if (trimmed.startsWith("#")) return { text: trimmed.replace(/^#+/, "").trim(), heading: true }
        return { text: (line.startsWith("   ") ? "    " : "") + trimmed, heading: false }
    }).filter(l => l)
}
