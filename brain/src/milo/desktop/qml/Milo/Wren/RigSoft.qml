import QtQuick
import QtQuick.Shapes

// An ellipse that fades to nothing at its edge: shadows, occlusion, light, blush (WrenRig.swift's softEllipse).
// Centred on (cx, cy), radii rx and ry, turned by the item's own `rotation` (degrees).
Item {
    id: soft
    property real cx
    property real cy
    property real rx: 1
    property real ry: 1
    property color color
    property real alpha: 1
    // The outline in the radius-50 circle's own space: the whole circle, or a part of it (rig.mjs's softClip).
    property string path: "M-50 0A50 50 0 1 0 50 0A50 50 0 1 0 -50 0Z"

    x: cx
    y: cy
    visible: alpha > 0.002 && path !== ""
    transform: Scale { xScale: soft.rx / 50; yScale: soft.ry / 50 }

    Shape {
        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: 0; centerY: 0; centerRadius: 50; focalX: 0; focalY: 0
                GradientStop { position: 0; color: Qt.rgba(soft.color.r, soft.color.g, soft.color.b, soft.alpha) }
                GradientStop { position: 0.45; color: Qt.rgba(soft.color.r, soft.color.g, soft.color.b, soft.alpha * 0.55) }
                GradientStop { position: 1; color: Qt.rgba(soft.color.r, soft.color.g, soft.color.b, 0) }
            }
            PathSvg { path: soft.path }
        }
    }
}
