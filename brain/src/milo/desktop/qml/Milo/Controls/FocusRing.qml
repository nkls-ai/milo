import QtQuick
import Milo

// The ring round a control that has keyboard focus, following its parent's shape. Put it inside the background.
Rectangle {
    property bool shown: false
    property real gap: 2

    anchors.fill: parent
    anchors.margins: -gap - border.width
    radius: parent.radius !== undefined ? parent.radius + gap + border.width : 6
    color: "transparent"
    border.width: 2
    border.color: Tones.fade(Theme.primary, 0.6)
    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { Spring { kind: "snappy" } }
}
