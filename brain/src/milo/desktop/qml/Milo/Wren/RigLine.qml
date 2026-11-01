import QtQuick
import QtQuick.Shapes

// A stroked line for the rig: round caps and joins unless `cap` says "flat", like WrenRig.swift's stroke.
Shape {
    id: shape
    property string path
    property color color
    property real lineWidth: 1
    property real alpha: 1
    property string cap: "round"

    visible: path !== "" && alpha > 0.002
    ShapePath {
        fillColor: "transparent"
        strokeColor: Qt.rgba(shape.color.r, shape.color.g, shape.color.b, shape.color.a * shape.alpha)
        strokeWidth: shape.lineWidth
        capStyle: shape.cap === "flat" ? ShapePath.FlatCap : ShapePath.RoundCap
        joinStyle: ShapePath.RoundJoin
        PathSvg { path: shape.path }
    }
}
