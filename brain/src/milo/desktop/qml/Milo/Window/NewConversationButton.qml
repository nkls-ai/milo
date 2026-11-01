import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls

// Start fresh: Milo forgets the last few minutes for this one.
T.AbstractButton {
    id: button
    hoverEnabled: true
    implicitHeight: 40
    Accessible.role: Accessible.Button
    Accessible.name: "New conversation"
    onClicked: conversations.newConversation()

    background: Rectangle {
        color: Tones.fade(Theme.primary, button.hovered ? 0.06 : 0)
        Behavior on color { ColorSpring { kind: "snappy" } }
        Rectangle { width: parent.width; height: 1; color: Theme.rule }
    }
    contentItem: RowLayout {
        spacing: 8
        Rectangle {
            Layout.leftMargin: 12
            implicitWidth: 18
            implicitHeight: 18
            radius: 9
            color: Tones.fade(Theme.primary, 0.14)
            Icon { anchors.centerIn: parent; name: "plus"; size: 11; color: Theme.primary; weight: "bold" }
        }
        MiloText { Layout.fillWidth: true; text: "New conversation"; size: 12.5; weight: "semibold"; rounded: true; ink: Theme.primary }
        KeyHint { keys: "Ctrl+N"; Layout.rightMargin: 12 }
    }
    Tip { text: "Start fresh: Milo forgets the last few minutes for this one"; shown: button.hovered }
}
