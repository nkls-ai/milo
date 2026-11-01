import QtQuick
import QtQuick.Shapes
import Milo
import Milo.Controls as Controls

// A filled circle whose tick draws itself: done, got it (VoiceCapsule.swift's DoneTick).
Item {
    id: tick
    property color color: Theme.primary
    property real drawn: 0

    implicitWidth: 16
    implicitHeight: 16
    Rectangle { anchors.fill: parent; radius: width / 2; color: tick.color }
    Controls.SmoothShape {
        anchors.fill: parent
        ShapePath {
            fillColor: "transparent"
            strokeColor: Theme.primaryInk
            strokeWidth: 1.8
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            // the check from 4.5 in, trimmed to how far it has drawn
            PathPolyline {
                path: {
                    const a = Qt.point(4.8, 8.3), b = Qt.point(7, 10.6), c = Qt.point(11.3, 5.5)
                    const first = 0.35, d = tick.drawn
                    if (d <= first) return [a, Qt.point(a.x + (b.x - a.x) * d / first, a.y + (b.y - a.y) * d / first)]
                    const u = (d - first) / (1 - first)
                    return [a, b, Qt.point(b.x + (c.x - b.x) * u, b.y + (c.y - b.y) * u)]
                }
            }
        }
    }
    SequentialAnimation on drawn {
        running: true
        PauseAnimation { duration: 50 }
        NumberAnimation { from: 0; to: 1; duration: Theme.reducedMotion ? 0 : 220; easing.type: Easing.OutQuad }
    }
}
