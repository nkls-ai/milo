pragma Singleton
import QtQuick
import MiloDesign  // Python registers Design (milo/desktop/design.py) here

// Milo's colours, sizes and motion, read from protocol/design.json through the `Design` singleton.
// Every view uses these names; none hard-codes a colour, radius or duration.
QtObject {
    readonly property var t: Design.tokens
    readonly property bool dark: Design.dark
    readonly property bool reducedMotion: Design.reducedMotion

    function pick(pair) { return pair[dark ? 1 : 0] }

    readonly property color primary: pick(t.colors.primary)
    readonly property color tint: pick(t.colors.tint)
    readonly property color accent: pick(t.colors.accent)
    readonly property color ink: pick(t.colors.ink)
    readonly property color glow: pick(t.colors.glow)
    // Text on `primary`. Not "onPrimary": QML reads on<Capital> as a signal handler and never binds it.
    readonly property color primaryInk: pick(t.colors.onPrimary)
    readonly property color card: pick(t.colors.card)
    readonly property color rule: pick(t.colors.rule)
    readonly property color muted: pick(t.colors.muted)
    readonly property color danger: pick(t.colors.danger)

    readonly property var wren: t.wren
    readonly property color talk: t.modes.talk
    readonly property color dictate: t.modes.dictate
    readonly property color think: t.modes.think
    readonly property color speak: t.modes.speak
    function modeColor(mode) { return mode === "dictate" ? dictate : mode === "talk" ? talk : primary }
    // What a recording mode wears on the surfaces next to Milo (Surface.color): lavender to talk, marigold to dictate.
    function voiceColor(mode) { return mode === "dictate" ? accent : primary }
    // The red of a recording light (meeting notes).
    readonly property color live: t.modes.live
    // Speakers in a meeting transcript, in turn (MeetingColors.speaker).
    readonly property var speakers: t.speakers
    // The wren as the rig draws him: Wren/WrenRig.qml.
    readonly property var rig: t.rig
    // The floating surfaces next to Milo: bubble and capsule radii, the text width, the figure's square.
    readonly property var surface: t.surface
    function fade(c, alpha) { return Qt.rgba(c.r, c.g, c.b, c.a * alpha) }

    readonly property var radius: t.radius
    readonly property var space: t.space
    readonly property var type: t.type
    // The first installed face wins: Windows 11 has "Segoe UI Variable" (no Text/Display families), Windows 10
    // only "Segoe UI", and Linux whatever the distribution ships.
    function installed(names) {
        const have = Qt.fontFamilies()
        for (const name of names)
            if (have.indexOf(name) >= 0)
                return name
        return names[names.length - 1]
    }
    readonly property string fontFamily: installed(["Segoe UI Variable", "Segoe UI", "SF Pro Text", "Inter",
                                                    "Cantarell", "Noto Sans", "DejaVu Sans", "sans-serif"])
    readonly property string roundedFamily: installed(["Segoe UI Variable", "Segoe UI", "SF Pro Rounded", "Inter",
                                                       "Cantarell", "Noto Sans", "DejaVu Sans", "sans-serif"])

    // Springs: see Motion.qml for the animation components built from these.
    readonly property var spring: t.motion.spring
    readonly property var gentle: t.motion.gentle
    readonly property var snappy: t.motion.snappy
    readonly property real reducedFade: t.motion.reducedFade
    readonly property real bob: reducedMotion ? 0 : t.motion.bob
}
