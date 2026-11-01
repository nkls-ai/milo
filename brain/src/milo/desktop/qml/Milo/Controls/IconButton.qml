import QtQuick
import QtQuick.Templates as T
import Milo

// A small round button with only an icon: Pause in the capsule, the × on a draft. `label` is what a screen reader
// says and the tooltip; `wash` false draws the icon alone until hovered.
T.AbstractButton {
    id: button
    property string iconName
    property string label
    property real size: 24
    property real iconSize: size * 0.44
    property color tint: Theme.ink
    property real tone: 0.75
    property bool wash: true

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: size
    implicitHeight: size
    scale: pressed ? 0.92 : 1
    Behavior on scale { Spring { kind: "snappy" } }
    Accessible.role: Accessible.Button
    Accessible.name: label
    Keys.onReturnPressed: clicked()

    background: Rectangle {
        radius: width / 2
        color: Tones.fade(Theme.primary, button.hovered ? 0.16 : button.wash ? 0.09 : 0)
        Behavior on color { ColorSpring { kind: "snappy" } }
        FocusRing { shown: button.visualFocus }
    }
    contentItem: Item {
        Icon {
            anchors.centerIn: parent
            name: button.iconName
            size: button.iconSize
            color: Tones.fade(button.tint, button.tone)
            weight: "bold"
        }
    }
    Tip { text: button.label; shown: button.hovered }
}
