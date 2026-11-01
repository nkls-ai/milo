import QtQuick
import QtQuick.Templates as T
import Milo
import Milo.Controls

// Minimize, maximize or restore, and close, drawn in Milo's ink: the frameless window's own buttons.
T.AbstractButton {
    id: button
    property string kind: "close"  // "minimize" | "maximize" | "restore" | "close"
    readonly property color ink: kind === "close" && hovered ? Theme.primaryInk : Tones.fade(Theme.ink, 0.6)

    implicitWidth: 34
    implicitHeight: 26
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    Accessible.role: Accessible.Button
    Accessible.name: ({ minimize: "Minimize", maximize: "Maximize", restore: "Restore", close: "Close" })[kind]

    background: Rectangle {
        radius: Theme.radius.small - 2
        color: button.kind === "close" ? Tones.fade(Tones.failed, button.hovered ? 0.9 : 0)
                                       : Tones.fade(Theme.ink, button.hovered ? 0.07 : 0)
        Behavior on color { ColorSpring { kind: "snappy" } }
    }
    contentItem: Item {
        Icon {
            anchors.centerIn: parent
            visible: button.kind === "close"
            name: "xmark"
            size: 12
            color: button.ink
        }
        Rectangle {
            anchors.centerIn: parent
            visible: button.kind === "minimize"
            width: 10
            height: 1.3
            color: button.ink
        }
        Rectangle {
            anchors.centerIn: parent
            visible: button.kind === "maximize" || button.kind === "restore"
            width: button.kind === "restore" ? 8 : 10
            height: width
            radius: 2
            color: "transparent"
            border.width: 1.3
            border.color: button.ink
        }
    }
    Tip { text: button.Accessible.name; shown: button.hovered }
}
