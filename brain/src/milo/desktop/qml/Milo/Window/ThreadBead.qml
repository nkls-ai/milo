import QtQuick
import Milo
import Milo.Controls

// A conversation's bead on the sidebar's thread: resting, the one going on (a ring that breathes), at work
// (marigold), or a task failed.
Item {
    id: bead
    property string state_: "rest"  // "rest" | "live" | "working" | "failed"
    property bool selected: false
    readonly property color tint: state_ === "working" ? Tones.running : Theme.primary
    implicitWidth: 11
    implicitHeight: 11
    Accessible.ignored: true

    Rectangle {
        id: breath
        anchors.centerIn: parent
        visible: bead.state_ === "live" || bead.state_ === "working"
        width: bead.width
        height: width
        radius: width / 2
        color: Tones.fade(bead.tint, 0.22)
        SequentialAnimation {
            running: breath.visible && !Theme.reducedMotion
            loops: Animation.Infinite
            ParallelAnimation {
                NumberAnimation { target: breath; property: "scale"; from: 1; to: 1.55; duration: 1600; easing.type: Easing.OutCubic }
                NumberAnimation { target: breath; property: "opacity"; from: 1; to: 0; duration: 1600; easing.type: Easing.OutCubic }
            }
        }
    }
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: bead.state_ === "rest" ? Theme.card : bead.state_ === "failed" ? Tones.failed : bead.tint
        border.width: bead.state_ === "rest" ? 1.5 : 0
        border.color: Tones.fade(Theme.primary, bead.selected ? 0.9 : 0.45)
    }
    Rectangle {
        anchors.centerIn: parent
        visible: bead.state_ === "working" || (bead.state_ === "rest" && bead.selected)
        width: bead.width - 7
        height: width
        radius: width / 2
        color: bead.state_ === "working" ? Theme.card : Theme.primary
    }
    MiloText {
        anchors.centerIn: parent
        visible: bead.state_ === "failed"
        text: "!"
        size: 8
        weight: "bold"
        ink: "white"
    }
}
