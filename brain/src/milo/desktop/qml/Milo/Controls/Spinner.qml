import QtQuick
import QtQuick.Shapes
import Milo

// A ring that turns while something is under way (ProgressView). Still under reduced motion.
Item {
    id: spinner
    property real size: 16
    property color color: Tones.fade(Theme.ink, 0.5)
    property real line: Math.max(1.5, size / 9)
    property real sweep: 0.7
    property bool running: visible

    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.Indicator
    Accessible.name: "Working"

    SmoothShape {
        id: ring
        anchors.fill: parent
        ShapePath {
            strokeColor: spinner.color
            strokeWidth: spinner.line
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: spinner.size / 2
                centerY: spinner.size / 2
                radiusX: (spinner.size - spinner.line) / 2
                radiusY: radiusX
                startAngle: -90
                sweepAngle: 360 * spinner.sweep
            }
        }
        RotationAnimator on rotation {
            from: 0
            to: 360
            duration: 1400
            loops: Animation.Infinite
            running: spinner.running && !Theme.reducedMotion
        }
    }
}
