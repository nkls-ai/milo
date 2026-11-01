import QtQuick
import Milo

// A lit dot, like the light on a camera: the mic is on (VoiceCapsule.swift's RecordingLight).
Item {
    property color color: Theme.primary
    implicitWidth: 16
    implicitHeight: 16
    Rectangle { anchors.centerIn: parent; width: 16; height: 16; radius: 8; color: Theme.fade(parent.color, 0.3) }
    Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: parent.color }
}
