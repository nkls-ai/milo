import QtQuick
import QtQuick.Shapes
import QtQuick.Effects
import Milo
import Milo.Controls as Controls

// The paper, hairline and soft lift of a surface floating next to Milo (Surface.swift's floatingSurface): Milo's
// paper a touch translucent, a shadow in his colour that falls from the paper alone (so text on it stays crisp),
// and a hairline, or a coloured edge for a surface that belongs to a mode.
//
//     FloatingSurface { anchors.fill: parent; radius: Theme.surface.capsuleRadius; edge: Theme.voiceColor(mode) }
//
// kind: "round" (a rounded rectangle of `radius`) or "bubble" (with a small tail at the bottom right pointing down
// at Milo, BubbleShape). Rounded rectangles rather than paths, so a surface whose size springs stays crisp.
Item {
    id: surface
    property string kind: "round"
    property real radius: Theme.surface.capsuleRadius
    // A coloured edge instead of the hairline; transparent for the hairline.
    property color edge: "transparent"

    readonly property bool bubble: kind === "bubble"
    readonly property real tail: bubble ? Theme.surface.bubbleTail : 0
    readonly property color paperColor: Theme.fade(Theme.tint, 0.97)
    readonly property color lineColor: edge.a > 0 ? edge : Theme.rule

    // the shadow's source: the paper without its tail, which casts too little to see
    Rectangle {
        id: paper
        width: parent.width
        height: parent.height - surface.tail
        radius: surface.bubble ? Theme.surface.bubbleRadius : surface.radius
        color: surface.paperColor
        visible: false
    }
    MultiEffect {
        anchors.fill: paper
        source: paper
        shadowEnabled: true
        shadowColor: Theme.fade(Theme.primary, 0.2)
        shadowBlur: 0.7
        blurMax: 24
        shadowVerticalOffset: 5
        autoPaddingEnabled: true
    }
    Shape {
        visible: surface.bubble
        x: parent.width - 34
        y: parent.height - surface.tail
        ShapePath {
            strokeColor: "transparent"
            fillColor: surface.paperColor
            PathSvg { path: "M-10 -1L6 -1L6 0Q6 4 8 8Q2 2 -10 0Z" }
        }
    }
    Rectangle {
        width: parent.width
        height: parent.height - surface.tail
        radius: surface.bubble ? Theme.surface.bubbleRadius : surface.radius
        color: "transparent"
        border.color: surface.lineColor
        border.width: 1
    }
    // the tail's own edge, drawn over the hairline where it leaves the bubble so the two run into each other
    Controls.SmoothShape {
        visible: surface.bubble
        x: parent.width - 44
        y: parent.height - surface.tail - 1
        width: 24; height: 11
        ShapePath {
            strokeColor: "transparent"
            fillColor: surface.paperColor
            PathSvg { path: "M0.5 0.4L15.6 0.4L15.6 1.6L0.5 1.6Z" }
        }
        ShapePath {
            fillColor: "transparent"
            strokeColor: surface.lineColor
            strokeWidth: 1
            PathSvg { path: "M16 1Q16 5 18 9Q12 3 0 1" }
        }
    }
}
