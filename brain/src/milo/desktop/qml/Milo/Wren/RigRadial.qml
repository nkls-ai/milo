import QtQuick
import QtQuick.Shapes
import Milo

// An outline filled with a radial gradient. By default the body's own: light lavender at `center`, deeper out to
// `radius`, so lids and cheek tufts painted with it vanish into him (WrenRig.swift's bodyGradient).
Shape {
    id: shape
    property string path
    property var center: [0, 0]
    property real radius: 108
    property color inner: Theme.rig.bodyHi
    property color middle: Theme.rig.bodyMid
    property color outer: Theme.rig.bodyLo
    // Where the middle colour sits, 0...1; two-colour gradients put it halfway.
    property real middleAt: 0.5

    visible: path !== ""
    ShapePath {
        strokeColor: "transparent"
        fillRule: ShapePath.WindingFill
        fillGradient: RadialGradient {
            centerX: shape.center[0]; centerY: shape.center[1]; centerRadius: shape.radius
            focalX: shape.center[0]; focalY: shape.center[1]
            GradientStop { position: 0; color: shape.inner }
            GradientStop { position: shape.middleAt; color: shape.middle }
            GradientStop { position: 1; color: shape.outer }
        }
        PathSvg { path: shape.path }
    }
}
