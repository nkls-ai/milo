import QtQuick
import Milo

// Three dots that rise in turn while Milo writes or listens. Still under reduced motion.
Row {
    id: dots
    property color color: Theme.primary
    property real dot: 6
    spacing: dot * 0.6
    Accessible.ignored: true

    Repeater {
        model: 3
        Rectangle {
            required property int index
            width: dots.dot
            height: dots.dot
            radius: dots.dot / 2
            color: dots.color
            SequentialAnimation on y {
                running: !Theme.reducedMotion
                loops: Animation.Infinite
                PauseAnimation { duration: index * 160 }
                NumberAnimation { from: 0; to: -dots.dot * 0.6; duration: 280; easing.type: Easing.OutQuad }
                NumberAnimation { from: -dots.dot * 0.6; to: 0; duration: 280; easing.type: Easing.InQuad }
                PauseAnimation { duration: (2 - index) * 160 + 300 }
            }
        }
    }
}
