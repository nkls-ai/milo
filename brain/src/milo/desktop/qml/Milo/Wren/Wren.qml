import QtQuick
import QtQuick.Effects
import Milo
import "pose.mjs" as Pose
import "motion.mjs" as Motion
import "director.mjs" as Director
import "life.mjs" as Life
import "clips.mjs" as Clips

// Milo, live (CharacterFigure + WrenView + CharacterLifeDriver on the Mac): the wren posed by his state and
// feelings, his idle life (blinks, glances, habits, the eyes following the pointer) and the moves between, sprung
// at the display's rate while anything moves and still otherwise.
//
//     Wren { width: 120; height: 120; brainState: presence.state; emotion: presence.emotion; level: presence.level }
//
// `still: true` draws the pose this input settles into, without the clock (renders, tests).
Item {
    id: root
    // "idle" | "listening" | "dictating" | "transcribing" | "thinking" | "speaking"
    property string brainState: "idle"
    // "neutral" | "happy" | "excited" | "thinking" | "concerned" | "sad" | "sleepy" | "confused"
    property string emotion: "neutral"
    // Drowsy, idle and quiet: he sleeps unless the pointer is on him.
    property bool asleep: false
    // Mic or voice loudness, 0...1.
    property real level: 0
    property bool connected: true
    // Words heard so far in the recording in progress: each new one may earn a nod.
    property int words: 0
    // A yes-or-no question waits on the user.
    property bool asking: false
    // He works in a window or drives the mouse and keys.
    property bool working: false
    // He takes meeting notes: a notepad in his wings.
    property bool noting: false
    // { kind: "perched" } | { kind: "flying", dx, dy } | { kind: "pointing", dx, dy }
    property var flight: ({ kind: "perched" })
    // The pointer relative to his centre in points, y up, or null; and -1 when the middle of the screen is to his
    // left, 1 to his right (the way he faces).
    property var cursor: null
    property real towardCentre: -1
    // Late at night he yawns now and then.
    property bool late: false
    property bool still: false
    property bool reducedMotion: Theme.reducedMotion
    readonly property bool small: width < 60

    // The pose the rig draws, and the director's view of the input.
    property var pose: Pose.rest()
    readonly property var input: Director.input({
        state: brainState, emotion: emotion, asleep: asleep, level: level, connected: connected, words: words,
        asking: asking, working: working, noting: noting, flight: flight, pose: lifePose })
    property var lifePose: Life.restPose()

    readonly property real seed: Math.floor(Math.random() * 4294967296)
    property var director: new Director.Director(seed)
    property var motion: new Motion.Motion()
    property var life: new Life.Life(seed + 1, 0)
    property real started: Date.now() / 1000
    property bool first: true

    function now() { return Date.now() / 1000 - started }

    // Plays one of his moves now (clips.mjs): "hop", "wiggle", "perk", "nod", "bob", ...
    function play(name) {
        if (still || reducedMotion || !Clips[name]) return
        motion.play(typeof Clips[name] === "function" ? Clips[name](lifePose.side) : Clips[name])
        run()
    }

    function lifeInput() {
        return { state: brainState, asleep: asleep, late: late, cursor: cursor, towardCentre: towardCentre }
    }

    // The life layer: a new pose only when it differs.
    function live() {
        if (still) return
        const next = life.update(lifeInput(), now())
        if (!Life.samePose(next, lifePose)) lifePose = next
        lifeTimer.restartFor(life.wake - now())
    }

    function direct() {
        if (still) {
            pose = Director.stillPose(input)
            return
        }
        director.direct(input, motion, now(), reducedMotion)
        if (first || !root.visible || reducedMotion && motion.playing.length) motion.snap()
        first = false
        pose = motion.pose
        run()
    }

    // Frames while anything moves, then a wake-up for the director's next beat.
    function run() {
        frames.running = !motion.settled && root.visible
        if (!frames.running) beatTimer.restartFor(director.wake - now())
    }

    onInputChanged: direct()
    onBrainStateChanged: live()
    onAsleepChanged: live()
    onCursorChanged: live()
    onTowardCentreChanged: live()
    onVisibleChanged: { live(); direct() }
    Component.onCompleted: { live(); direct() }

    FrameAnimation {
        id: frames
        onTriggered: {
            if (root.director.wake <= root.now()) root.director.direct(root.input, root.motion, root.now(), root.reducedMotion)
            root.motion.advance(Math.min(frameTime, 0.1))
            root.pose = root.motion.pose
            if (root.motion.settled) root.run()
        }
    }
    Timer {
        id: beatTimer
        function restartFor(seconds) {
            stop()
            if (!isFinite(seconds)) return
            interval = Math.max(10, seconds * 1000)
            start()
        }
        onTriggered: { root.director.direct(root.input, root.motion, root.now(), root.reducedMotion); root.run() }
    }
    Timer {
        id: lifeTimer
        function restartFor(seconds) {
            stop()
            if (!isFinite(seconds)) return
            interval = Math.max(10, seconds * 1000)
            start()
        }
        onTriggered: root.live()
    }
    // The pointer: watched 10 times a second awake, 4 asleep, by whoever sets `cursor`.

    Item {
        id: figure
        anchors.fill: parent
        opacity: root.connected ? 1 : 0.55
        layer.enabled: !root.connected
        layer.effect: MultiEffect { saturation: -0.8 }

        WrenRig {
            anchors.fill: parent
            pose: root.pose
            small: root.small
            // a slow breath: deeper and slower asleep, none in the air or with reduced motion
            breath: root.still || root.reducedMotion || root.flight.kind === "flying" ? 0
                  : Director.sleeping(root.input) ? 0.022 : 0.012
            breathPeriod: Director.sleeping(root.input) ? 5.2 : 3.6
        }
        FigureMarks {
            anchors.centerIn: parent
            scale: Math.min(root.width, root.height) / 120
            shown: Director.shown(root.input)
            sleeping: Director.sleeping(root.input)
            small: root.small
            frozen: root.still || root.reducedMotion
        }
    }
}
