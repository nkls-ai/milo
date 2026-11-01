import QtQuick
import Milo

// The recording light: red and breathing slowly while it records, a grey pause sign while paused.
Item {
    id: light
    property bool paused: false
    implicitWidth: 16
    implicitHeight: 16
    Accessible.ignored: true

    Icon {
        anchors.centerIn: parent
        visible: light.paused
        name: "pause.circle"
        size: 14
        color: Tones.fade(Theme.ink, 0.45)
    }
    Rectangle {
        id: halo
        visible: !light.paused
        anchors.fill: parent
        radius: width / 2
        color: Tones.live
        opacity: 0.28
        // A slow breath, 1.8 s a cycle like the Mac's sine; held still under reduced motion.
        SequentialAnimation on opacity {
            running: halo.visible && !Theme.reducedMotion
            loops: Animation.Infinite
            NumberAnimation { from: 0.18; to: 0.38; duration: 900; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.38; to: 0.18; duration: 900; easing.type: Easing.InOutSine }
        }
    }
    Rectangle {
        visible: !light.paused
        anchors.centerIn: parent
        width: 9
        height: 9
        radius: 4.5
        color: Tones.live
    }
}
