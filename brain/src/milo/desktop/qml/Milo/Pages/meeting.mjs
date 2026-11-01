// A meeting's words for its page (MeetingPage.swift): the line under the title, the notes without what the header
// and the To-dos tab already show, the consent line.
import * as Format from "format.mjs"

export const consent = "Milo is taking notes for me. They stay on my computer."

// A meeting_status phase that is going on: recording, paused or writing the notes.
export function current(status, id) {
    return !!status && status.id !== "" && status.id === id && ["recording", "paused", "writing"].indexOf(status.phase) >= 0
}

// Recording or paused: Pause and Stop show.
export function live(status) { return !!status && (status.phase === "recording" || status.phase === "paused") }

// "Taking notes · 12:34 · Zoom", "Paused at 12:34 · nothing goes into the notes now", "Writing your notes · …".
export function liveLine(status, elapsed) {
    const app = status.app ? " · " + status.app : ""
    switch (status.phase) {
    case "paused": return "Paused at " + Format.clock(elapsed) + " · nothing goes into the notes now"
    case "writing": return status.step ? "Writing your notes · " + status.step : "Writing your notes…"
    default: return "Taking notes · " + Format.clock(elapsed) + app
    }
}

// The end of a live transcript: the words come about a minute late, and this says so.
export function lagLine(phase, step, empty) {
    if (phase === "paused") return "Paused. Nothing said now goes into the notes."
    if (phase === "writing") return step ? step + "…" : "Writing your notes…"
    return empty ? "Listening… the first words show up in about a minute." : "Listening… the last minute shows up shortly."
}

// "Thu 30 Oct, 14:00 · 30 min · Zoom · with Anna and Ben".
export function notesLine(notes) {
    const parts = []
    const started = Format.parse(notes.started)
    if (started) parts.push(Format.shortDayTime(started))
    if (notes.duration > 0) parts.push(Format.length(notes.duration))
    if (notes.app) parts.push(notes.app)
    if (notes.people && notes.people.length) parts.push("with " + Format.list(notes.people))
    return parts.join(" · ")
}

// notes.md for the Notes tab: without its title and date line (the header has them) and its To-dos (their tab).
export function notesBody(markdown) {
    const lines = String(markdown || "").split("\n")
    let i = 0
    const skipBlank = () => { while (i < lines.length && lines[i].trim() === "") ++i }
    skipBlank()
    if (i < lines.length && /^#\s/.test(lines[i])) {
        ++i
        skipBlank()
        // The paragraph under the title: the date, the app and who was there.
        if (i < lines.length && !/^(#|-|\*|\d+\.)/.test(lines[i].trim())) while (i < lines.length && lines[i].trim() !== "") ++i
    }
    const kept = []
    let skipping = false
    for (; i < lines.length; ++i) {
        const heading = /^(#{1,2})\s+(.*)$/.exec(lines[i])
        if (heading) {
            const title = heading[2].toLowerCase()
            skipping = title.startsWith("to-do") || title.startsWith("todo")
        }
        if (!skipping) kept.push(lines[i])
    }
    return kept.join("\n").trim()
}

// "[The whole transcript](transcript.md)": a link to Milo's own file, which opens the tab rather than the file.
export function ownLink(url) { return /(^|\/)transcript\.md$/.test(String(url)) }

// The questions in the meeting's conversation and Milo's answers, from the user's first question on.
export function questions(entries) {
    const all = entries || []
    const first = all.findIndex(e => e.kind === "user")
    return first < 0 ? [] : all.slice(first).filter(e => e.kind === "user" || e.kind === "milo")
}

// The speakers in order of first line.
export function names(lines) {
    const seen = []
    for (const line of lines || []) if (seen.indexOf(line.who) < 0) seen.push(line.who)
    return seen
}

function escape(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// **bold**, *italic*, `code` and [links](url) as rich text, everything else escaped.
function inline(text) {
    return escape(text)
        .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
        .replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2">$1</a>')
}

// Notes markdown as blocks for NotesText (MarkdownBlock.parse on the Mac): headings, paragraphs, bullets, numbered
// items and to-dos with their depth, quotes and rules, each with the air the Mac leaves before it.
export function blocks(markdown) {
    const out = []
    let paragraph = []
    const push = block => {
        const previous = out.length ? out[out.length - 1].kind : ""
        const listy = k => ["bullet", "numbered", "todo"].indexOf(k) >= 0
        block.gap = !out.length ? 0 : block.kind === "heading" ? (block.level <= 2 ? 22 : 16)
                  : previous === "heading" ? 8 : listy(previous) && listy(block.kind) ? 6 : 11
        out.push(block)
    }
    const flush = () => {
        if (paragraph.length) push({ kind: "paragraph", html: inline(paragraph.join(" ")) })
        paragraph = []
    }
    for (const raw of String(markdown || "").split("\n")) {
        const line = raw.replace(/\s+$/, "")
        const depth = Math.floor((/^\s*/.exec(line)[0].length) / 2)
        const text = line.trim()
        let m
        if (!text) { flush(); continue }
        if ((m = /^(#{1,6})\s+(.*)$/.exec(text))) { flush(); push({ kind: "heading", level: m[1].length, html: inline(m[2]) }) }
        else if ((m = /^[-*]\s+\[([ xX])\]\s+(.*)$/.exec(text))) { flush(); push({ kind: "todo", done: m[1] !== " ", depth: depth, html: inline(m[2]) }) }
        else if ((m = /^[-*]\s+(.*)$/.exec(text)) && !/^(-{3,}|\*{3,})$/.test(text)) { flush(); push({ kind: "bullet", depth: depth, html: inline(m[1]) }) }
        else if ((m = /^(\d+)[.)]\s+(.*)$/.exec(text))) { flush(); push({ kind: "numbered", number: +m[1], depth: depth, html: inline(m[2]) }) }
        else if ((m = /^>\s?(.*)$/.exec(text))) { flush(); push({ kind: "quote", html: inline(m[1]) }) }
        else if (/^(-{3,}|\*{3,}|_{3,})$/.test(text)) { flush(); push({ kind: "rule" }) }
        else paragraph.push(text)
    }
    flush()
    return out
}
