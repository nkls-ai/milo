import QtQuick
import Milo

// A small count on a marigold capsule, beside a tab's name: "To-dos 2".
Rectangle {
    id: badge
    property int count: 0
    property color tint: Theme.accent

    implicitWidth: Math.max(implicitHeight, label.implicitWidth + 11)
    implicitHeight: label.implicitHeight + 2
    radius: height / 2
    color: tint
    Accessible.role: Accessible.StaticText
    Accessible.name: String(count)

    MiloText {
        id: label
        anchors.centerIn: parent
        text: badge.count
        size: 10.5
        weight: "bold"
        rounded: true
        tabular: true
        ink: Theme.primaryInk
    }
}
