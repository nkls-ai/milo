import QtQuick
import QtQuick.Shapes
import QtQuick.Effects
import Milo
import "shapes.mjs" as Shapes

// The glowing edge around where Milo works, in his colours (WorkingOutlineView.swift's WorkingEdge): a band from
// glow through marigold to lavender, breathing slowly, or still with reduced motion.
Item {
    id: edge
    property real radius: 14
    property real lineWidth: 5
    property real blur: 1.5
    property real glow: 0.55
    readonly property bool effects: GraphicsInfo.api !== GraphicsInfo.Software

    Shape {
        id: band
        anchors.fill: parent
        // blurred through the effect below; Qt's software renderer has no effects, so there it shows sharp
        visible: edge.blur <= 0 || !edge.effects
        ShapePath {
            strokeColor: "transparent"
            fillRule: ShapePath.OddEvenFill
            fillGradient: LinearGradient {
                x1: 0; y1: 0; x2: edge.width; y2: edge.height
                GradientStop { position: 0; color: Theme.glow }
                GradientStop { position: 0.5; color: Theme.accent }
                GradientStop { position: 1; color: Theme.primary }
            }
            PathSvg {
                path: Shapes.roundRect(edge.width, edge.height, edge.radius) + " "
                      + Shapes.roundRect(edge.width, edge.height, edge.radius, edge.lineWidth)
            }
        }
    }
    MultiEffect {
        anchors.fill: parent
        visible: edge.blur > 0 && edge.effects
        source: band
        blurEnabled: true
        blur: 1
        blurMax: Math.ceil(edge.blur * 2)
    }
    opacity: Theme.reducedMotion ? 0.75 : glow
    SequentialAnimation on glow {
        running: !Theme.reducedMotion && edge.visible
        loops: Animation.Infinite
        NumberAnimation { from: 0.55; to: 0.9; duration: 1600; easing.type: Easing.InOutQuad }
        NumberAnimation { from: 0.9; to: 0.55; duration: 1600; easing.type: Easing.InOutQuad }
    }
}
