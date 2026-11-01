import QtQuick
import QtQuick.Shapes

// A Shape that stays smooth and always draws: plain GPU triangles in a small 4× multisampled layer. Qt 6.8's curve
// renderer drops shapes, most of all ones whose outline animates (a check drawing itself); the software renderer
// smooths by itself, so there the layer is skipped. Give it a size: the layer covers only its bounds.
//
//     SmoothShape { anchors.fill: parent; ShapePath { ... } }
Shape {
    layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
    layer.samples: 4
    layer.smooth: true
}
