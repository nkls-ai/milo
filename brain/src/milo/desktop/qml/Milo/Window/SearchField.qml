import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// The search field: Ctrl+F, a magnifier, Enter opens the first hit and Esc clears it.
Rectangle {
    id: field
    function focusField() { editor.forceActiveFocus(); editor.selectAll() }

    implicitHeight: 30
    radius: Theme.radius.small - 1
    color: Theme.card
    border.width: 1
    border.color: editor.activeFocus ? Tones.fade(Theme.primary, 0.5) : Theme.rule
    Behavior on border.color { ColorSpring { kind: "snappy" } }

    RowLayout {
        anchors { fill: parent; leftMargin: 9; rightMargin: 7 }
        spacing: 6
        Icon { name: "magnifyingglass"; size: 11.5; color: Tones.fade(Theme.ink, 0.45) }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            TextInput {
                id: editor
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                text: conversations.search
                color: Theme.ink
                selectionColor: Tones.fade(Theme.primary, 0.35)
                selectedTextColor: Theme.ink
                font.family: Theme.fontFamily
                font.pixelSize: 13
                clip: true
                selectByMouse: true
                Accessible.role: Accessible.EditableText
                Accessible.name: "Search conversations"
                onTextEdited: conversations.setSearch(text)
                onAccepted: conversations.openFirst()
                Keys.onEscapePressed: { conversations.setSearch(""); focus = false }
            }
            MiloText {
                anchors.verticalCenter: parent.verticalCenter
                visible: editor.text === ""
                text: "Search"
                size: 12.5
                tone: 0.45
            }
        }
        KeyHint { visible: editor.text === ""; keys: "Ctrl+F" }
        IconButton {
            visible: editor.text !== ""
            iconName: "xmark.circle"
            label: "Clear the search"
            size: 18
            wash: false
            onClicked: conversations.setSearch("")
        }
    }
}
