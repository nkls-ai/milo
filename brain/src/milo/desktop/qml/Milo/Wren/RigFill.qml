import QtQuick
import QtQuick.Shapes

// A filled outline for the rig, in a solid colour or a vertical gradient from `fill` (at y `from`) to `fillEnd` (at y
// `to`), the way WrenRig.swift's fillLinear paints. `alpha` fades it.
Shape {
    id: shape
    property string path
    property color fill
    property color fillEnd: fill
    property real from: 0
    property real to: 1
    property real alpha: 1

    visible: path !== "" && alpha > 0.002
    ShapePath {
        strokeColor: "transparent"
        fillRule: ShapePath.WindingFill
        fillGradient: LinearGradient {
            x1: 0; y1: shape.from; x2: 0; y2: shape.to
            GradientStop { position: 0; color: Qt.rgba(shape.fill.r, shape.fill.g, shape.fill.b, shape.fill.a * shape.alpha) }
            GradientStop {
                position: 1
                color: Qt.rgba(shape.fillEnd.r, shape.fillEnd.g, shape.fillEnd.b, shape.fillEnd.a * shape.alpha)
            }
        }
        PathSvg { path: shape.path }
    }
}
