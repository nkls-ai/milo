// Words about tasks and helpers, as the Mac's TaskPage.swift, HelperViews.swift and TranscriptEntry.swift say them.

// A task's title, or the first sentence of what was asked.
export function headline(entry) {
    if (entry.title) return entry.title
    const text = String(entry.text || "")
    return (text.split(/[.!?\n]/)[0] || text).trim()
}

// helpers[].status: whether it still holds a place in the queue.
export function active(status) { return status === "queued" || status === "working" || status === "needs_you" }

// "waiting its turn", "working", … after a helper's name.
export function helperWords(status) {
    return { queued: "waiting its turn", working: "working", needs_you: "needs your answer", done: "done",
             failed: "couldn't finish", stopped: "stopped" }[status] || status
}

// A task's status for a screen reader: "working on it", "done", "couldn't finish".
export function statusWords(status) {
    return { running: "working on it", done: "done", failed: "couldn't finish" }[status] || status
}

// The status pill: "Working on it", "Done", "Couldn't finish".
export function statusHeadline(status) {
    return { running: "Working on it", done: "Done", failed: "Couldn't finish" }[status] || status
}

// "1 step", "3 steps".
export function steps(n) { return n === 1 ? "1 step" : n + " steps" }

// The line under a task card's headline: its step while it works, its result once done.
export function line(entry, helper) {
    const count = steps((entry.steps || []).length)
    const last = (entry.steps || [])[(entry.steps || []).length - 1]
    switch (entry.status) {
    case "running":
        if (helper && helper.step) return helper.step
        return last ? last.title + " · " + count : "Starting…"
    case "done": {
        const result = String(entry.result || "").split("\n")[0]
        return result ? result : "Done · " + count
    }
    default:
        return entry.result ? entry.result : "Couldn't finish"
    }
}

// A step's icon by its kind.
export function stepIcon(kind) {
    return { command: "terminal", read: "doc.text", edit: "pencil", search: "magnifyingglass", web: "globe",
             app: "macwindow", tool: "wrench" }[kind] || "sparkle"
}

// "renamed.txt" for "~/Pictures/Friday/renamed.txt".
export function fileName(path) { return String(path).split(/[\\/]/).filter(p => p).pop() || path }

// "in Friday" for ~/Pictures/Friday/renamed.txt; "in your home folder" for ~/x.
export function folder(path) {
    const parts = String(path).split(/[\\/]/)
    parts.pop()
    const dir = parts.join("/")
    return dir === "~" ? "in your home folder" : "in " + (parts.filter(p => p).pop() || dir)
}

// A meeting conversation's preview without "Notes from “Weekly sync”: " in front.
export function meetingSummary(preview) {
    const text = String(preview || "")
    const colon = text.indexOf("”: ")
    return text.startsWith("Notes from “") && colon >= 0 ? text.slice(colon + 3) : text
}
