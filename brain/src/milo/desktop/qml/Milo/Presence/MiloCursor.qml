import QtQuick
import QtQuick.Shapes
import QtQuick.Effects
import Milo
import "shapes.mjs" as Shapes

// Milo's own pointer, in his colours (CursorView.swift): never the system cursor, so the user's own pointer is
// untouched. A ring ripples out on a click; a caret and a little "Milo" tag show while he types. The tip is at (0, 0).
Item {
    id: cursor
    // "none" | "click" | "typing"
    property string gesture: "none"
    // Rises each time a click lands, to ripple again.
    property int clicks: 0

    width: 72
    height: 96

    // the ring of a click
    Rectangle {
        id: ripple
        x: -6; y: -6
        width: 34; height: 34; radius: 17
        color: "transparent"
        border.color: Theme.accent
        border.width: 2.5
        opacity: 0
        visible: cursor.gesture === "click"
        transformOrigin: Item.Center
        ParallelAnimation {
            id: ring
            NumberAnimation { target: ripple; property: "scale"; from: 0.4; to: 1.6; duration: 500; easing.type: Easing.OutQuad }
            NumberAnimation { target: ripple; property: "opacity"; from: 0.9; to: 0; duration: 500; easing.type: Easing.OutQuad }
        }
    }
    onClicksChanged: ring.restart()
    onGestureChanged: if (gesture === "click") ring.restart()

    // an arrow in his colours with a soft white edge and a little shadow, so it reads on any background
    Shape {
        id: arrow
        width: 22; height: 30
        // drawn through the shadow effect below; plain on Qt's software renderer, which has no effects
        visible: GraphicsInfo.api === GraphicsInfo.Software
        layer.enabled: !visible; layer.samples: 4  // smooth edges
        ShapePath {
            strokeColor: Theme.fade("white", 0.95)
            strokeWidth: 1.5
            joinStyle: ShapePath.RoundJoin
            fillGradient: LinearGradient {
                x1: 0; y1: 0; x2: 0; y2: 30
                GradientStop { position: 0; color: Theme.glow }
                GradientStop { position: 1; color: Theme.primary }
            }
            PathSvg { path: Shapes.arrow(22, 30) }
        }
    }
    MultiEffect {
        visible: !arrow.visible
        anchors.fill: arrow
        source: arrow
        shadowEnabled: true
        shadowColor: Theme.fade(Theme.primary, 0.5)
        shadowBlur: 0.5
        blurMax: 8
        shadowVerticalOffset: 1
        autoPaddingEnabled: true
    }

    // typing: a blinking caret and his name
    Row {
        x: 20; y: 30
        spacing: 4
        opacity: cursor.gesture === "typing" ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.InOutQuad } }
        Rectangle {
            id: caret
            width: 2.5; height: 20; radius: 1
            color: Theme.primary
            SequentialAnimation on opacity {
                running: cursor.gesture === "typing" && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { from: 1; to: 0.2; duration: 500; easing.type: Easing.InOutQuad }
                NumberAnimation { from: 0.2; to: 1; duration: 500; easing.type: Easing.InOutQuad }
            }
        }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: tag.implicitWidth + 12; height: tag.implicitHeight + 4
            radius: height / 2
            color: Theme.fade(Theme.primary, 0.92)
            Text {
                id: tag
                anchors.centerIn: parent
                text: "Milo"
                color: Theme.primaryInk
                font { family: Theme.fontFamily; pixelSize: 10; weight: Font.DemiBold }
            }
        }
    }
}
