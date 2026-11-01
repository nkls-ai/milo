import QtQuick
import Milo

// A task's status as a small seal: a ring that turns while it works ("?" when it waits for you), a check when done,
// a cross when it failed. `status` is a task's: "running" | "done" | "failed".
Item {
    id: seal
    property string status: "running"
    property bool needsYou: false
    property real size: 26

    readonly property color tint: status === "running" ? (needsYou ? Theme.think : Tones.running) : Tones.status(status)
    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Tones.fade(seal.tint, 0.14)
        Behavior on color { ColorSpring {} }
    }
    Spinner {
        anchors.centerIn: parent
        visible: seal.status === "running"
        size: seal.size - 10
        line: 2
        color: seal.tint
    }
    MiloText {
        anchors.centerIn: parent
        visible: seal.status === "running" && seal.needsYou
        text: "?"
        size: seal.size * 0.42
        weight: "bold"
        rounded: true
        ink: seal.tint
    }
    Icon {
        anchors.centerIn: parent
        visible: seal.status !== "running"
        name: seal.status === "done" ? "check" : "xmark"
        size: seal.size * (seal.status === "done" ? 0.46 : 0.4)
        color: seal.tint
        weight: "bold"
    }
}
