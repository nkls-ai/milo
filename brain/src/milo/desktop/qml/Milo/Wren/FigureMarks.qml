import QtQuick
import QtQuick.Shapes
import Milo
import Milo.Controls as Controls

// Floating marks by his head (CharacterFigure.swift's FigureMarks): a rising "z" while asleep, a bobbing "?" when
// confused, a sparkle when excited. Drawn in the 120 pt box; his crown is near (60, 30) and he faces left, so the
// marks sit behind his head. `frozen` holds each at its first pose (renders, reduced motion).
Item {
    id: root
    property string shown: "neutral"
    property bool sleeping: false
    property bool small: false
    property bool frozen: false

    width: 120
    height: 120

    // A "z" drifting up and away while it fades, two of them out of step.
    Repeater {
        model: root.shown === "sleepy" && root.sleeping ? 2 : 0
        Text {
            id: zed
            required property int index
            readonly property real t: (root.clock + index * 0.5) % 1
            // keys at 0 (dx -2, dy 4, scale 0.7, clear), 0.25 (in place, solid), 1 (dx 7, dy -14, scale 1.1, clear)
            readonly property real u: t < 0.25 ? t / 0.25 : (t - 0.25) / 0.75
            x: 84 + index * 7 - 12 + (t < 0.25 ? -2 + 2 * u : 7 * u)
            y: 30 - index * 5 - 12 + (t < 0.25 ? 4 - 4 * u : -14 * u)
            width: 24; height: 24
            horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            scale: t < 0.25 ? 0.7 + 0.3 * u : 1 + 0.1 * u
            opacity: t < 0.25 ? u : 1 - u
            text: "z"
            color: Theme.rig.bodyMid
            font { family: Theme.roundedFamily; pixelSize: index === 0 ? 15 : 11; bold: true }
        }
    }
    // The z's clock: the second runs 1.3 s behind the first.
    property real clock: 0
    NumberAnimation on clock {
        running: root.shown === "sleepy" && root.sleeping && !root.frozen
        from: 0; to: 1; duration: 2600; loops: Animation.Infinite
    }

    // A question mark bobbing behind his head.
    Text {
        id: question
        visible: root.shown === "confused"
        property real bob: 3
        x: 86 - 12; y: 20 - 14 + bob
        width: 24; height: 28
        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
        text: "?"
        color: Theme.rig.scarfLo
        font { family: Theme.roundedFamily; pixelSize: 20; weight: Font.Black }
        SequentialAnimation on bob {
            running: question.visible && !root.frozen
            loops: Animation.Infinite
            NumberAnimation { from: 3; to: -3; duration: 1000; easing.type: Easing.InOutQuad }
            NumberAnimation { from: -3; to: 3; duration: 1000; easing.type: Easing.InOutQuad }
        }
    }

    // A sparkle on the other side, pulsing and rocking.
    Controls.SmoothShape {
        id: sparkle
        visible: root.shown === "excited" && !root.small
        property real pulse: 0
        x: 120 - 86 + 4 - 12; y: 20 + 6 - 12
        width: 24; height: 24
        scale: 0.85 + 0.3 * pulse
        rotation: -10 + 20 * pulse
        ShapePath {
            strokeColor: "transparent"
            fillColor: Theme.rig.scarfHi
            PathSvg { path: "M12 4Q13 11 20 12Q13 13 12 20Q11 13 4 12Q11 11 12 4Z" }
        }
        SequentialAnimation on pulse {
            running: sparkle.visible && !root.frozen
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: 1; duration: 600; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1; to: 0; duration: 600; easing.type: Easing.InOutQuad }
        }
    }
}
