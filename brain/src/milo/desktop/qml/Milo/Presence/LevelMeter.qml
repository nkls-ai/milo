import QtQuick
import Milo
import "voice.mjs" as Voice

// A meter that follows the voice (VoiceCapsule.swift's LevelMeter): the newest level in the middle, older ones
// moving outwards, sampled at a steady 20 Hz so silence settles instead of freezing a shape.
Row {
    id: meter
    property real level: 0
    property color color: Theme.primary
    // newest first
    property var history: [0, 0, 0, 0]

    spacing: 2.5
    height: 16
    Repeater {
        model: 7
        Rectangle {
            required property int index
            readonly property int age: Math.abs(index - 3)
            anchors.verticalCenter: parent.verticalCenter
            width: 2.5
            radius: 1.25
            height: 3 + 13 * Voice.levelHeight(meter.history[age])
            color: Theme.fade(meter.color, 1 - age * 0.14)
            Behavior on height { Spring { response: 0.16; dampingFraction: 0.75 } }
        }
    }
    Timer {
        interval: 50
        repeat: true
        running: meter.visible
        onTriggered: meter.history = [meter.level].concat(meter.history.slice(0, 3))
    }
}
