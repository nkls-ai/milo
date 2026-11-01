import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// One conversation in the sidebar: its bead on the thread, a mark for its kind, the title, the time and a line of
// preview. `row` is one of conversations.rows (presentation/sidebar.py).
Item {
    id: item
    property var row: ({})
    property bool selected: false
    readonly property real bead: 15.5  // the bead's centre from the top, level with the title
    readonly property bool meetingLive: item.row.active === true && item.row.mark === "meeting"

    implicitHeight: text.implicitHeight + 14
    implicitWidth: 200

    // The thread runs through the day's group, bead to bead.
    Rectangle {
        x: 17 - 0.75
        width: 1.5
        y: item.row.first ? item.bead : -7
        height: (item.row.last ? item.bead : item.height + 7) - y
        color: Tones.fade(Theme.primary, 0.2)
    }
    ThreadBead {
        x: 17 - width / 2
        y: item.bead - height / 2
        state_: item.row.bead || "rest"
        selected: item.selected
    }

    ColumnLayout {
        id: text
        x: 35
        y: 7
        width: item.width - x - 8
        spacing: 2

        RowLayout {
            spacing: 5
            Layout.fillWidth: true
            Icon {
                visible: (item.row.mark || "") !== ""
                name: ({ meeting: "person.2", routine: "arrow.loop", phone: "iphone" })[item.row.mark] || ""
                size: 10
                color: item.row.mark === "phone" ? Tones.fade(Theme.ink, 0.55) : Theme.primary
            }
            MiloText {
                Layout.fillWidth: true
                text: item.row.title || ""
                size: 12.5
                weight: item.selected || item.row.live ? "semibold" : "medium"
                rounded: true
            }
            MiloText {
                text: item.row.time || ""
                size: 10.5
                tabular: true
                tone: 0.42
            }
        }
        RowLayout {
            spacing: 5
            Layout.fillWidth: true
            Rectangle {
                visible: item.meetingLive
                implicitWidth: 6
                implicitHeight: 6
                radius: 3
                color: Tones.live
            }
            MiloText {
                Layout.fillWidth: true
                text: item.row.subtitle || ""
                size: 11.5
                weight: item.meetingLive ? "medium" : "regular"
                tone: item.row.active ? 0.7 : 0.52
            }
        }
    }
}
