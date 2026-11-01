import QtQuick
import Milo

// A step's bead on its thread. Running: an amber ring that breathes. Done: a filled dot with a check. Failed: a cross.
// `status` is a step's: "running" | "done" | "failed".
Item {
    id: bead
    property string status: "running"
    implicitWidth: 14
    implicitHeight: 14
    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        radius: 7
        color: bead.status === "running" ? "transparent" : Tones.status(bead.status)
        border.width: bead.status === "running" ? 1.5 : 0
        border.color: Tones.running
    }
    Rectangle {
        id: core
        visible: bead.status === "running"
        anchors.fill: parent
        anchors.margins: 4
        radius: width / 2
        color: Tones.running
        // Breathing, as the Mac's .easeInOut(duration: 0.8).repeatForever(): a loop, not a response to a change.
        SequentialAnimation on scale {
            running: core.visible && !Theme.reducedMotion
            loops: Animation.Infinite
            NumberAnimation { from: 0.55; to: 1; duration: 800; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1; to: 0.55; duration: 800; easing.type: Easing.InOutSine }
        }
    }
    Icon {
        anchors.centerIn: parent
        visible: bead.status !== "running"
        name: bead.status === "done" ? "check" : "xmark"
        size: 8
        color: Theme.primaryInk
        weight: "bold"
    }
}
