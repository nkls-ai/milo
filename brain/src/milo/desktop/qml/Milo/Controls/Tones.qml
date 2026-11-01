pragma Singleton
import QtQuick
import Milo

// Colours derived from Theme for what a task or a meeting is doing (WindowColors and MeetingColors on the Mac).
// The mode colours are bright for Milo's body; on light paper they are darkened so they read as text.
QtObject {
    function fade(c, alpha) { return Theme.fade(c, alpha) }
    function darken(c, share) { return Qt.rgba(c.r * (1 - share), c.g * (1 - share), c.b * (1 - share), c.a) }
    function onPaper(c, share) { return Theme.dark ? c : darken(c, share) }

    readonly property color running: onPaper(Theme.think, 0.25)
    readonly property color done: onPaper(Theme.dictate, 0.35)
    readonly property color failed: onPaper(Theme.talk, 0.18)

    // "running" | "working" | "done" | "failed" | "stopped", as tasks and helpers name them.
    function status(s) { return s === "done" ? done : s === "failed" || s === "stopped" ? failed : running }

    // MeetingColors on the Mac: the recording light and other speakers in turn, from design.json.
    readonly property color live: Theme.live
    readonly property var speakers: Theme.speakers
    function speaker(name, names) {
        if (name === "You") return Theme.primary
        if (name === "Others") return fade(Theme.ink, 0.45)
        const others = (names || []).filter(n => n !== "You" && n !== "Others")
        let i = others.indexOf(name)
        if (i < 0) { i = 0; for (let k = 0; k < name.length; ++k) i = (i * 31 + name.charCodeAt(k)) >>> 0 }
        return speakers[i % speakers.length]
    }
}
