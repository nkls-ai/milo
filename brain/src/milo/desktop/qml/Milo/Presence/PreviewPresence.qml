import QtQuick

// A stand-in for the `presence` object the shell provides (desktop/viewmodels), with the same properties, signals
// and slots, for previews and tests.
QtObject {
    // "" | "armed" | "listening" | "caught" | "transcribing" | "pasted" | "thinking" | "offline"
    property string phase: ""
    // "talk" | "dictate" | ""
    property string mode: ""
    property bool handsFree: false
    // The brain's state: "idle" | "listening" | "dictating" | "transcribing" | "thinking" | "speaking"
    property string state: "idle"
    property string emotion: "neutral"
    // Mic or voice level 0...1, about 30 times a second.
    property real level: 0
    property string bubble: ""
    // What the user said, shown small over the answer.
    property string heard: ""
    // The live transcript of the recording in progress.
    property string partial: ""
    // Milo says the bubble aloud now: its words show in step with his voice.
    property bool speaking: false
    property bool connected: true
    property bool helpersActive: false
    property string hint: ""
    // On screen; false while he is away (Presence).
    property bool shown: true
    signal celebrate()
    signal nudge()
    function openWindow() { opened++ }
    function stop() { stopped++ }
    function cancel() { cancelled++ }

    // The names viewmodels/presence.py adds: the colour the capsule wears, recording, the line for screen readers,
    // the bubble's pacing {shown, fresh, alpha} (undefined: the whole text), helpers, Stop, the eye.
    property string colorMode: ""
    property bool recording: false
    property string spoken: ""
    property var reveal: undefined
    property var helpers: []
    property bool canStop: false
    property bool looking: false
    // The `confirm` event waiting ({id, question, money, always, choices}), an empty map when none.
    property var question: ({})
    function answer(id) { answered = id }
    // A button under the bubble: {title, icon, hint, kind}, an empty map when none.
    property var bubbleAction: ({})
    function performBubbleAction() { acted++ }
    function summon() {}
    function dismiss() {}
    function setHeld(held) {}
    function setPointing(pointing) {}

    // Only here, for previews: what the shell's `store.meeting` would hold, the pointer in screen coordinates for
    // his eyes, and drowsiness.
    property var meeting: null
    property var cursor: undefined
    property bool drowsy: false

    // What the stand-in was asked to do, for tests.
    property int opened: 0
    property int stopped: 0
    property int cancelled: 0
    property int acted: 0
    property string answered: ""
}
