import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// A conversation's title, what kind it is and when; double-click the title to rename it. "Going on" marks the one
// Milo is in now. `info` is conversations.header (presentation/sidebar.header).
Item {
    id: header
    property var info: ({})
    property bool live: false
    property bool editing: false
    readonly property color mark: info.warm ? Theme.accent : Theme.primary

    implicitHeight: 52

    function start() { name.text = info.title || ""; editing = true; name.focusAndSelect() }
    function save() {
        if (!editing) return
        editing = false
        conversations.rename(info.id, name.text)
    }

    RowLayout {
        anchors { fill: parent; leftMargin: 18; rightMargin: 18 }
        spacing: 11

        Rectangle {
            implicitWidth: 30
            implicitHeight: 30
            radius: 9
            color: Tones.fade(header.mark, 0.13)
            Icon {
                anchors.centerIn: parent
                name: ({ meeting: "person.2", routine: "arrow.loop", phone: "iphone" })[header.info.mark] || "bubble.left.and.bubble.right"
                size: 13
                color: header.mark
                filled: header.info.mark === "chat"
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            MiloText {
                visible: !header.editing
                Layout.fillWidth: true
                text: header.info.title || ""
                size: 15
                weight: "bold"
                rounded: true
                Accessible.role: Accessible.Heading
                MouseArea { id: title; anchors.fill: parent; hoverEnabled: true; onDoubleClicked: header.start() }
                Tip { text: "Double-click to rename"; shown: title.containsMouse }
            }
            MiloField {
                id: name
                visible: header.editing
                Layout.fillWidth: true
                size: 14
                placeholder: "Name"
                onAccepted: header.save()
                onCancelled: header.editing = false
                onActiveFocusChanged: if (!activeFocus) header.save()
            }
            MiloText {
                Layout.fillWidth: true
                text: header.info.subtitle || ""
                size: 11
                tone: 0.5
            }
        }
        Rectangle {
            visible: header.live
            implicitWidth: going.implicitWidth + 16
            implicitHeight: going.implicitHeight + 8
            radius: height / 2
            color: Tones.fade(Theme.primary, 0.1)
            RowLayout {
                id: going
                anchors.centerIn: parent
                spacing: 6
                ThreadBead { state_: "live" }
                MiloText { text: "Going on"; size: 10.5; weight: "semibold"; rounded: true; ink: Theme.primary }
            }
            HoverHandler { id: hover }
            Tip { text: "Milo is in this conversation now: what you say next goes on here"; shown: hover.hovered }
        }
    }
    Rule { anchors { left: parent.left; right: parent.right; bottom: parent.bottom } }
}
