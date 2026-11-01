import QtQuick
import Milo
import "voice.mjs" as Voice

// Three dots in a slow wave, drawn from the clock so they keep moving however long he thinks. With reduced motion
// they glow in turn instead of moving (VoiceCapsule.swift's ThinkingDots, with its exact wave).
Row {
    id: dots
    property color color: Theme.primary
    property real t: 0

    spacing: 4
    height: 16
    Repeater {
        model: 3
        Rectangle {
            required property int index
            readonly property real wave: Voice.wave(dots.t, index)
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: Theme.reducedMotion ? 0 : -3 * wave
            width: 6; height: 6; radius: 3
            color: dots.color
            opacity: Theme.reducedMotion ? 0.35 + 0.65 * wave : 0.55 + 0.45 * wave
        }
    }
    FrameAnimation {
        running: dots.visible
        onTriggered: dots.t += frameTime
    }
}
