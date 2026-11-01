import QtQuick
import Milo
import Milo.Controls

// An app's name in a capsule with a small × that takes it off the list ("Ask me again for Zoom").
Rectangle {
    id: chip
    property string name
    signal remove()

    implicitWidth: row.implicitWidth + 18
    implicitHeight: row.implicitHeight + 8
    radius: height / 2
    color: Tones.fade(Theme.ink, 0.07)

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 4
        MiloText { anchors.verticalCenter: parent.verticalCenter; text: chip.name; size: 12; weight: "medium"; rounded: true; tone: 0.8 }
        IconButton {
            objectName: "remove"
            anchors.verticalCenter: parent.verticalCenter
            iconName: "xmark"
            label: "Ask again for " + chip.name
            size: 16
            iconSize: 9
            wash: false
            onClicked: chip.remove()
        }
    }
}
