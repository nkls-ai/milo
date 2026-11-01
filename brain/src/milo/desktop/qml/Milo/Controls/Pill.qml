import QtQuick
import Milo

// A word in a capsule: "Working on it" in its status colour on a wash of it (StatusPill), or `filled` for a plan
// ("Max") in Milo's colour.
Rectangle {
    id: pill
    property string text
    property color tint: Theme.primary
    property bool filled: false
    property real size: 10.5

    implicitWidth: label.implicitWidth + 14
    implicitHeight: label.implicitHeight + 3
    radius: height / 2
    color: filled ? tint : Tones.fade(tint, 0.13)
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    MiloText {
        id: label
        anchors.centerIn: parent
        text: pill.text
        size: pill.size
        weight: "bold"
        rounded: true
        ink: pill.filled ? Theme.primaryInk : pill.tint
    }
}
