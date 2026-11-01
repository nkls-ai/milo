import QtQuick
import QtQuick.Shapes
import Milo

// An empty dashed ring until something is done, then a filled circle whose tick draws itself, with a soft burst.
Item {
    id: badge
    property bool done: false
    property real size: 24
    implicitWidth: size
    implicitHeight: size
    Accessible.ignored: true

    // The tick's box and line, as the Mac's CheckBadge.Tick: short stroke then long, in 46 % of the badge.
    readonly property real box: size * 0.46
    readonly property real line: size * 0.11
    // The tick's length in line widths, so a single dash of `drawn` × it draws that share of the tick.
    readonly property real length: box * 1.556 / line

    SmoothShape {
        anchors.fill: parent
        opacity: badge.done ? 0 : 1
        Behavior on opacity { Spring {} }
        ShapePath {
            strokeColor: Tones.fade(Theme.primary, 0.28)
            strokeWidth: 1.6
            fillColor: "transparent"
            strokeStyle: ShapePath.DashLine
            dashPattern: [3 / 1.6, 3 / 1.6]
            PathAngleArc {
                centerX: badge.size / 2
                centerY: badge.size / 2
                radiusX: badge.size / 2 - 1
                radiusY: badge.size / 2 - 1
                sweepAngle: 360
            }
        }
    }
    // The burst: a glow ring that grows and fades as the badge fills.
    Rectangle {
        id: burst
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.color: Theme.glow
        border.width: 2
        opacity: 0
        ParallelAnimation {
            id: burstAnimation
            NumberAnimation { target: burst; property: "scale"; from: 1; to: 1.9; duration: 600; easing.type: Easing.OutCubic }
            NumberAnimation { target: burst; property: "opacity"; from: 0.8; to: 0; duration: 600; easing.type: Easing.OutCubic }
        }
    }
    onDoneChanged: if (done && !Theme.reducedMotion) burstAnimation.restart()

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Theme.primary
        scale: badge.done ? 1 : 0.2
        opacity: badge.done ? 1 : 0
        Behavior on scale { Spring {} }
        Behavior on opacity { Spring {} }
    }
    SmoothShape {
        x: (badge.size - badge.box) / 2
        y: x
        width: badge.box
        height: badge.box
        visible: tick.drawn > 0.01
        ShapePath {
            id: tick
            property real drawn: badge.done ? 1 : 0
            Behavior on drawn {
                SequentialAnimation {
                    PauseAnimation { duration: Theme.reducedMotion ? 0 : 120 }
                    Spring {}
                }
            }
            strokeColor: Theme.primaryInk
            strokeWidth: badge.line
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            strokeStyle: ShapePath.DashLine
            dashPattern: [Math.max(0.001, tick.drawn * badge.length), badge.length * 2]
            startX: 0
            startY: badge.box * 0.55
            PathLine { x: badge.box * 0.36; y: badge.box * 0.92 }
            PathLine { x: badge.box; y: badge.box * 0.1 }
        }
    }
}
