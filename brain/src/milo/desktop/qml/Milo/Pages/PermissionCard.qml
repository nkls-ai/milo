import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// One permission on the setup page: what Milo does with it, a clear button, and a tick that draws itself once the
// system says yes. `row` is {permission, title, reason, state, button}. The Mac's little looping scene is a still
// icon here.
Card {
    id: card
    property var row: ({})
    signal fix()
    readonly property bool granted: row.state === "granted"

    padding: 12
    objectName: "permission-" + row.permission

    RowLayout {
        spacing: 14
        Rectangle {
            Layout.alignment: Qt.AlignTop
            implicitWidth: 52
            implicitHeight: 52
            radius: 14
            color: Theme.tint
            border.color: Theme.rule
            Icon {
                anchors.centerIn: parent
                name: ({ microphone: "mic", accessibility: "hand.raised", screenRecording: "macwindow",
                         calendars: "calendar", reminders: "list.bullet", automation: "pencil.line",
                         contacts: "person" })[card.row.permission] || "sparkles"
                size: 22
                color: Theme.primary
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6
            RowLayout {
                MiloText { Layout.fillWidth: true; text: card.row.title || ""; size: 15; weight: "semibold"; rounded: true }
                CheckBadge { done: card.granted }
            }
            MiloText { Layout.fillWidth: true; text: card.row.reason || ""; size: 12.5; tone: 0.7; wrapMode: Text.WordWrap }
            MiloText { visible: card.granted; text: "Done"; size: 12; weight: "semibold"; rounded: true; ink: Theme.primary }
            MiloButton {
                objectName: "fix"
                visible: !card.granted
                Layout.topMargin: 2
                text: card.row.button || "Open settings"
                onClicked: card.fix()
            }
        }
    }
}
