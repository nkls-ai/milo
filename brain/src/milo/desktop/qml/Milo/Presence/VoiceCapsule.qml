import QtQuick
import Milo
import Milo.Controls as Controls
import "voice.mjs" as Voice

// The capsule over Milo that shows his ears and his head (VoiceCapsule.swift): a light the instant the key goes
// down, a level meter that follows the voice with the words so far, "Got it" when the key comes up, then dots while
// he works out what was said and thinks. One surface that changes shape, so each step reads as the next one: its
// size springs from one phase to the next while the picture inside cross-fades.
//
// It grows out of its bottom-right corner (no fade: the light is there in the first frame and only grows), and goes
// quickly, so a tap or a shortcut never leaves a fading light behind.
Item {
    id: capsule
    // phase, mode, handsFree, partial, heard and level, as the presence object names them
    property string phase: ""
    property string mode: ""
    property bool handsFree: false
    property string partial: ""
    property string heard: ""
    property real level: 0

    // What it shows: the phase, kept while it goes away.
    property string showing: phase
    readonly property bool armed: showing === "armed"
    readonly property color tone: showing === "offline" ? Theme.fade(Theme.ink, 0.35)
                                : Theme.voiceColor(showing === "pasted" ? "dictate" : showing === "thinking" ? "talk" : mode)
    readonly property string words: Voice.words(showing, handsFree, partial, heard)
    property real thinkingSince: 0
    property real thinkingFor: 0
    readonly property string label: showing === "thinking" ? Voice.thinkingLabel(thinkingFor, words !== "")
                                                           : Voice.label(showing, mode, words !== "")

    implicitWidth: surface.width
    implicitHeight: surface.height
    transformOrigin: Item.BottomRight
    visible: opacity > 0.002
    Accessible.role: Accessible.StatusBar
    Accessible.name: Voice.spoken(showing, mode)
    Accessible.description: words

    // Shown long enough that a size change is a change of shape, not its first size.
    property bool settled: false
    onPhaseChanged: {
        if (phase !== "" && showing === "") settled = false
        if (phase !== "") { showing = phase; Qt.callLater(() => capsule.settled = true) }
        if (phase === "thinking") { thinkingSince = Date.now() / 1000; thinkingFor = 0 }
        if (phase !== "") {
            leave.stop()
            if (opacity < 1) { scale = Theme.reducedMotion ? 1 : 0.55; opacity = 1 }
            scale = 1
        } else {
            leave.start()
        }
    }
    Component.onCompleted: { opacity = phase === "" ? 0 : 1; scale = 1 }
    Behavior on scale { enabled: !leave.running; Spring {} }
    ParallelAnimation {
        id: leave
        NumberAnimation { target: capsule; property: "scale"; to: Theme.reducedMotion ? 1 : 0.85; duration: 120; easing.type: Easing.OutQuad }
        NumberAnimation { target: capsule; property: "opacity"; to: 0; duration: 120; easing.type: Easing.OutQuad }
        onFinished: capsule.showing = ""
    }
    Timer {
        interval: 1000; repeat: true
        running: capsule.showing === "thinking"
        onTriggered: capsule.thinkingFor = Date.now() / 1000 - capsule.thinkingSince
    }

    // The surface, sized by its content with Milo's spring.
    Item {
        id: surface
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        readonly property real padX: capsule.armed ? 8 : 12
        width: Math.ceil(content.implicitWidth + 2 * padX)
        height: Math.ceil(content.implicitHeight + 14)
        // springs between phases; takes its first size at once, so the light is the first thing that shows
        Behavior on width { enabled: capsule.settled; Spring {} }
        Behavior on height { enabled: capsule.settled; Spring {} }

        FloatingSurface {
            anchors.fill: parent
            radius: Theme.surface.capsuleRadius
            edge: Voice.recording(capsule.showing) ? Theme.fade(capsule.tone, 0.5) : "transparent"
        }
        Column {
            id: content
            x: surface.padX
            y: 7
            spacing: 6
            Row {
                spacing: 8
                // the picture, in a fixed frame so the capsule only grows to the right
                Item {
                    width: capsule.armed ? 14 : 30
                    height: 16
                    Appear {
                        anchors.centerIn: parent
                        shown: capsule.showing === "armed"; from: 0.6
                        RecordingLight { color: capsule.tone }
                    }
                    Appear {
                        anchors.centerIn: parent
                        shown: capsule.showing === "listening"; from: 1
                        LevelMeter { level: capsule.level; color: capsule.tone }
                    }
                    Loader {
                        // a fresh tick each time, so it draws itself again
                        anchors.centerIn: parent
                        active: capsule.showing === "caught" || capsule.showing === "pasted"
                        sourceComponent: Appear { from: 0.5; DoneTick { color: capsule.tone } }
                    }
                    Appear {
                        anchors.centerIn: parent
                        shown: ["transcribing", "thinking", "offline"].indexOf(capsule.showing) >= 0; from: 1
                        VoiceDots { color: capsule.tone }
                    }
                }
                Text {
                    visible: capsule.label !== ""
                    anchors.verticalCenter: parent.verticalCenter
                    text: capsule.label
                    color: Theme.fade(Theme.ink, capsule.showing === "offline" ? 0.6 : 0.9)
                    font { family: Theme.roundedFamily; pixelSize: 12; weight: Font.DemiBold }
                }
                // a double tap locked the mic on
                Controls.Icon {
                    visible: capsule.showing === "listening" && capsule.handsFree
                    anchors.verticalCenter: parent.verticalCenter
                    name: "lock"; filled: true; size: 10; weight: "bold"
                    color: capsule.tone
                    Accessible.name: "Hands-free"
                }
            }
            Text {
                visible: capsule.words !== ""
                width: Math.min(implicitWidth, Theme.surface.textWidth - 24)
                text: capsule.words
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideLeft
                color: Theme.fade(Theme.ink, Voice.recording(capsule.showing) ? 0.95 : 0.6)
                font { family: Theme.fontFamily; pixelSize: 12 }
            }
        }
    }
}
