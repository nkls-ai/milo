import QtQuick
import QtQuick.Shapes
import Milo
import Milo.Controls

// The marigold check on a done card's corner. It draws itself in a moment after the card lands; under reduced motion,
// or `still`, it is simply there.
Rectangle {
    id: check
    property bool still: false
    property real drawn: still || Theme.reducedMotion ? 1 : 0

    // The tick's box and line, as CheckShape in a 20-point circle with 5.5 points of air.
    readonly property real box: width - 11
    readonly property real line: 2.2
    readonly property real length: box * 1.53 / line

    width: 20
    height: 20
    radius: 10
    color: Theme.accent
    border.color: Theme.tint
    border.width: 2
    Accessible.ignored: true

    // A one-off draw after landing, as the Mac's .easeOut(duration: 0.32).delay(0.28).
    SequentialAnimation on drawn {
        running: !check.still && !Theme.reducedMotion
        PauseAnimation { duration: 280 }
        NumberAnimation { to: 1; duration: 320; easing.type: Easing.OutCubic }
    }

    SmoothShape {
        x: 5.5
        y: 5.5
        width: check.box
        height: check.box
        visible: check.drawn > 0.01
        ShapePath {
            strokeColor: Theme.primaryInk
            strokeWidth: check.line
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            strokeStyle: ShapePath.DashLine
            dashPattern: [Math.max(0.001, check.drawn * check.length), check.length * 2]
            startX: 0
            startY: check.box * 0.55
            PathLine { x: check.box * 0.36; y: check.box * 0.9 }
            PathLine { x: check.box; y: check.box * 0.12 }
        }
    }
}
