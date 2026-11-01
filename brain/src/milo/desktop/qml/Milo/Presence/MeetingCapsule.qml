import QtQuick
import Milo
import Milo.Controls as Controls
import "voice.mjs" as Voice

// The capsule over Milo while he takes meeting notes (MeetingCapsule.swift): a red light, "Taking notes", the time so
// far, Pause and a clear Stop. Paused, the light goes grey and Pause turns into Go on. After Stop it says what he
// writes until the notes are ready. A click on the words opens the meeting's page.
//
// `meeting` is the `meeting_status` event (phase "recording" | "paused" | "writing" | "", step, error, elapsed).
// Pause, Go on, Stop and a click on the words come out as pause(on), stop() and open().
Item {
    id: capsule
    property var meeting: null
    signal pause(bool on)
    signal stop()
    signal open()
    readonly property bool live: !!meeting && (meeting.phase === "recording" || meeting.phase === "paused")
    readonly property bool active: live || !!meeting && meeting.phase === "writing"
    property var showing: meeting
    // The clock ticks here between the shell's updates.
    property real elapsed: 0
    onMeetingChanged: if (meeting && meeting.phase) { showing = meeting; elapsed = meeting.elapsed || 0 }
    Component.onCompleted: if (meeting) elapsed = meeting.elapsed || 0

    implicitWidth: surface.width
    implicitHeight: surface.height
    transformOrigin: Item.BottomRight
    opacity: active ? 1 : 0
    scale: active || Theme.reducedMotion ? 1 : 0.85
    visible: opacity > 0.002
    Behavior on opacity { Spring {} }
    Behavior on scale { Spring {} }
    Accessible.role: Accessible.Grouping
    Accessible.name: "Meeting notes"

    Timer {
        interval: 1000; repeat: true
        running: capsule.visible && !!capsule.showing && capsule.showing.phase === "recording"
        onTriggered: capsule.elapsed += 1
    }

    Item {
        id: surface
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        readonly property bool live: !!capsule.showing && capsule.showing.phase !== "writing"
        width: Math.ceil(row.implicitWidth + 11 + (live ? 5 : 12))
        height: Math.max(34, Math.ceil(row.implicitHeight + 10))
        Behavior on width { Spring {} }

        FloatingSurface {
            anchors.fill: parent
            radius: height / 2
            edge: capsule.showing && capsule.showing.phase === "recording" ? Theme.fade(Theme.live, 0.45) : "transparent"
        }
        Row {
            id: row
            x: 11
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8

            // the words, a button that opens the meeting's page
            Row {
                spacing: 7
                anchors.verticalCenter: parent.verticalCenter
                readonly property var s: capsule.showing || ({})
                VoiceDots { visible: parent.s.phase === "writing"; width: 30; color: Theme.primary; anchors.verticalCenter: parent.verticalCenter }
                Column {
                    visible: parent.s.phase === "writing"
                    spacing: 1
                    anchors.verticalCenter: parent.verticalCenter
                    Text {
                        text: "Writing your notes"
                        color: Theme.fade(Theme.ink, 0.9)
                        font { family: Theme.roundedFamily; pixelSize: 12; weight: Font.DemiBold }
                    }
                    Text {
                        visible: text !== ""
                        text: capsule.showing && capsule.showing.step ? capsule.showing.step : ""
                        color: Theme.fade(Theme.ink, 0.6)
                        font { family: Theme.fontFamily; pixelSize: 11 }
                    }
                }
                // something can't be heard: the light turns into a warning, the bubble says what and how to fix it
                Controls.LiveLight {
                    visible: parent.s.phase !== "writing" && !parent.s.error
                    anchors.verticalCenter: parent.verticalCenter
                    paused: parent.s.phase === "paused"
                }
                Controls.Icon {
                    visible: parent.s.phase !== "writing" && !!parent.s.error
                    anchors.verticalCenter: parent.verticalCenter
                    name: "exclamationmark.triangle"; filled: true; size: 12; color: Theme.accent
                }
                Text {
                    visible: parent.s.phase !== "writing"
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.s.phase === "paused" ? "Paused" : "Taking notes"
                    color: Theme.fade(Theme.ink, 0.9)
                    font { family: Theme.roundedFamily; pixelSize: 12; weight: Font.DemiBold }
                }
                Text {
                    visible: parent.s.phase !== "writing"
                    anchors.verticalCenter: parent.verticalCenter
                    text: Voice.clock(capsule.elapsed)
                    color: Theme.fade(Theme.ink, 0.6)
                    font { family: Theme.roundedFamily; pixelSize: 12; weight: Font.Medium; features: { "tnum": 1 } }
                }
                TapHandler { onTapped: capsule.open() }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
            }
            Controls.MiloButton {
                visible: surface.live
                anchors.verticalCenter: parent.verticalCenter
                kind: "secondary"; size: "small"; iconOnly: true
                readonly property bool paused: !!capsule.showing && capsule.showing.phase === "paused"
                iconName: paused ? "play" : "pause.circle"
                text: paused ? "Go on" : "Pause"
                tip: text
                onClicked: capsule.pause(!paused)
            }
            Controls.MiloButton {
                visible: surface.live
                anchors.verticalCenter: parent.verticalCenter
                kind: "primary"; size: "small"
                iconName: "stop"
                text: "Stop"
                tip: "Stop taking notes and write them up"
                onClicked: capsule.stop()
            }
        }
    }
}
