import QtQuick
import Milo
import Milo.Controls

// A helper as a still mini figure with a mark on its corner for how it is doing (HelperBird.Mini and HelperMark):
// "z" while it waits its turn, "?" when it needs you, a check when done, a cross when it couldn't finish, a square
// when stopped; nothing while it works. `status` is a helpers entry's.
Item {
    id: mini
    property string status: "working"
    property real size: 30

    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    WrenSlot {
        anchors.fill: parent
        size: mini.size
        asleep: mini.status === "queued"
        mood: mini.status === "working" ? "thinking" : "happy"
        opacity: mini.status === "stopped" || mini.status === "queued" ? 0.6 : 1
    }
    Rectangle {
        visible: mini.status !== "working"
        x: parent.width - width + 3
        y: -1
        width: 12
        height: 12
        radius: 6
        border.color: Qt.rgba(1, 1, 1, 0.8)
        border.width: 1
        color: mini.status === "queued" ? Theme.tint : mini.status === "needs_you" ? Theme.think
             : mini.status === "done" ? Tones.done : mini.status === "failed" ? Tones.failed : Tones.fade(Theme.muted, 1)
        MiloText {
            anchors.centerIn: parent
            visible: mini.status === "queued" || mini.status === "needs_you"
            text: mini.status === "queued" ? "z" : "?"
            size: 8
            weight: "bold"
            rounded: true
            ink: mini.status === "queued" ? Theme.primary : Theme.wren.face
        }
        Icon {
            anchors.centerIn: parent
            visible: mini.status !== "queued" && mini.status !== "needs_you"
            name: mini.status === "done" ? "check" : mini.status === "failed" ? "xmark" : "stop"
            filled: mini.status === "stopped"
            size: 7
            weight: "bold"
            color: "#FFFFFF"
        }
    }
}
