import QtQuick
import QtQuick.Templates as T
import Milo

// A tooltip in Milo's paper (`.help` on the Mac): appears a moment after the pointer rests on its parent.
T.ToolTip {
    id: tip
    property bool shown: false

    visible: shown && text !== ""
    delay: 600
    y: -implicitHeight - 6
    x: (parent ? parent.width - implicitWidth : 0) / 2
    padding: 7
    implicitWidth: Math.min(implicitContentWidth + leftPadding + rightPadding, 280)
    horizontalPadding: 9

    contentItem: MiloText {
        text: tip.text
        size: 11.5
        wrapMode: Text.WordWrap
    }
    background: Rectangle {
        radius: 8
        color: Theme.tint
        border.color: Theme.rule
    }
    enter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 1000 * Theme.reducedFade; easing.type: Easing.OutCubic } }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 1000 * Theme.reducedFade; easing.type: Easing.OutCubic } }
}
