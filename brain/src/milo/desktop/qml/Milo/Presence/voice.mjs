// The voice capsule's words and pictures (VoiceCapsule.swift; presentation/voice_phase.py decides the phase).
// phase: "" | "armed" | "listening" | "caught" | "transcribing" | "pasted" | "thinking" | "offline".

export const recording = phase => phase === "armed" || phase === "listening" || phase === "caught"

// The label next to the indicator; "" where the picture says enough. `words`: live words show under it.
export function label(phase, mode, words) {
    switch (phase) {
    case "listening": return mode === "dictate" ? "Dictating" : "Listening"
    case "caught": return "Got it"
    case "transcribing": return mode === "dictate" ? "Writing it down" : words ? "" : "One moment"
    case "pasted": return "Pasted"
    case "thinking": return words ? "" : "Thinking"
    case "offline": return "Waking up"
    default: return ""
    }
}

// Thinking for longer than a moment says so, so a slow answer never looks stuck.
export function thinkingLabel(seconds, words) {
    if (seconds < 6) return label("thinking", "", words)
    return seconds < 20 ? "Still on it" : "Taking a while"
}

// A short name for screen readers.
export function spoken(phase, mode) {
    switch (phase) {
    case "armed": return "Milo is listening"
    case "listening": return mode === "dictate" ? "Milo is taking dictation" : "Milo is listening"
    case "caught": return "Milo got it"
    case "transcribing": return mode === "dictate" ? "Milo is writing it down" : "Milo is working out what you said"
    case "pasted": return "Pasted"
    case "thinking": return "Milo is thinking"
    case "offline": return "Milo is waking up"
    default: return ""
    }
}

// The last `limit` characters, cut at a word, so the newest words stay visible.
export function tail(text, limit = 140) {
    if (text.length <= limit) return text
    const end = text.slice(-(limit + 1))
    const space = end.indexOf(" ")
    return "…" + (space >= 0 ? end.slice(space + 1) : end)
}

// The words under the label: what was heard so far, then what the brain made of it.
export function words(phase, handsFree, partial, heard) {
    switch (phase) {
    case "listening":
        if (partial) return tail(partial)
        return handsFree ? "Tap the key again when you're done. Esc cancels." : ""
    case "caught": case "transcribing": return partial ? tail(partial) : ""
    case "thinking": return heard ? tail("“" + heard + "”") : ""
    default: return ""
    }
}

// Meter bar height 0...1 for a mic level: room noise stays flat, a normal voice fills most of it.
export const levelHeight = level => Math.pow(Math.min(1, Math.max(0, (level - 0.04) / 0.7)), 0.7)

// 0...1 for dot `dot` at `t` seconds: each rises a little after the one before, then all rest a moment.
export function wave(t, dot) {
    let phase = (t / 1.1 - dot * 0.16) % 1
    if (phase < 0) phase += 1
    return Math.max(0, Math.sin(phase * 2 * Math.PI))
}

// "12:04" or "1:02:03" for a meeting's length.
export function clock(seconds) {
    const s = Math.max(0, Math.floor(seconds)), h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60
    const pad = v => (v < 10 ? "0" : "") + v
    return h > 0 ? h + ":" + pad(m) + ":" + pad(s % 60) : m + ":" + pad(s % 60)
}

// How Milo's cursor moves (CursorGlide.swift): a short eased glide, quicker for short hops, bowed a little to the side.
export const glideDuration = distance => Math.min(0.6, Math.max(0.18, 0.16 + distance / 2600))

export function glidePoint(start, end, t) {
    const s = 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3)
    const dx = end.x - start.x, dy = end.y - start.y
    const length = Math.max(Math.hypot(dx, dy), 0.001)
    const bow = Math.min(40, length * 0.08) * Math.sin(Math.PI * s)
    // y counts down here (Qt), up on the Mac: the bow keeps the Mac's side
    return { x: start.x + dx * s + dy / length * bow, y: start.y + dy * s - dx / length * bow }
}

// Where a hidden cursor appears before gliding to `target`: a little up and to the left of it.
export const glideEntry = target => ({ x: target.x - 70, y: target.y - 50 })
