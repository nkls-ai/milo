import QtQuick
import Milo
import Milo.Controls

// A shortcut, quietly: "Ctrl+N".
Rectangle {
    id: hint
    property string keys
    implicitWidth: label.implicitWidth + 8
    implicitHeight: label.implicitHeight + 2
    radius: 4
    color: "transparent"
    border.color: Tones.fade(Theme.ink, 0.12)
    Accessible.ignored: true

    MiloText {
        id: label
        anchors.centerIn: parent
        text: hint.keys
        size: 9.5
        weight: "medium"
        rounded: true
        tone: 0.35
    }
}
