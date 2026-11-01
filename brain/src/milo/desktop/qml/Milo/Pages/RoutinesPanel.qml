import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls
import "format.mjs" as Format
import "routines.mjs" as Routines
import "wire.mjs" as Wire

// The Routines section (RoutinesPanel): a line that opens into the user's routines, each with its schedule, its last
// run and Run now. Closed, it takes one line and says what comes up next.
//
// Inputs
//   routines: the `routines` event's routines, [{id, name, description, schedule, paused, last_run, next_run, inputs,
//             problem}]
//   open:     shown open (the owner may keep it, as the Mac keeps it in AppStorage)
//   now:      the clock, for "next: Monday report, tomorrow at 09:00"
// Output
//   command({"type": "routine", id, action: "run" | "pause" | "resume" | "delete"})
Rectangle {
    id: panel
    property var routines: []
    property bool open: false
    property var now: new Date()
    // A Date, or the brain's "2026-11-01T10:00" (previews pass one).
    readonly property var clock: typeof now === "string" ? Format.parse(now) : now
    signal command(var message)

    // Rows shown before the list scrolls.
    readonly property int rows: 4
    readonly property var next: Routines.nextUp(routines)

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + 16
    color: Tones.fade(Theme.ink, 0.05)
    clip: true
    Behavior on implicitHeight { Spring {} }

    ColumnLayout {
        id: column
        x: 16
        y: 8
        width: parent.width - 32
        spacing: 8

        T.AbstractButton {
            id: toggle
            objectName: "toggle"
            Layout.fillWidth: true
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            implicitHeight: line.implicitHeight
            Accessible.role: Accessible.Button
            Accessible.name: "Routines"
            Accessible.description: panel.open ? "shown" : "hidden"
            Keys.onReturnPressed: clicked()
            onClicked: panel.open = !panel.open
            contentItem: Item {}
            RowLayout {
                id: line
                width: parent.width
                spacing: 6
                Icon {
                    name: "chevron.right"
                    size: 10
                    weight: "bold"
                    color: Tones.fade(Theme.ink, 0.6)
                    rotation: panel.open ? 90 : 0
                    Behavior on rotation { Spring {} }
                }
                MiloText {
                    text: panel.routines.length === 1 ? "1 routine" : panel.routines.length + " routines"
                    size: 11
                    weight: "semibold"
                    rounded: true
                    tone: 0.6
                }
                MiloText {
                    Layout.fillWidth: true
                    visible: !panel.open && panel.next !== null
                    text: panel.next ? "· next: " + panel.next.name + ", " + Routines.when(Format.parse(panel.next.next_run), panel.clock) : ""
                    size: 11
                    tone: 0.6
                }
                Item { Layout.fillWidth: true; visible: panel.open || panel.next === null }
            }
            FocusRing { shown: toggle.visualFocus; radius: 4 }
            Tip { text: panel.open ? "Hide your routines" : "Show your routines"; shown: toggle.hovered }
        }

        Flickable {
            id: list
            Layout.fillWidth: true
            visible: panel.open
            implicitHeight: Math.min(rowsColumn.implicitHeight, panel.rows * 52)
            contentHeight: rowsColumn.implicitHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            T.ScrollBar.vertical: MiloScrollBar {}
            ColumnLayout {
                id: rowsColumn
                width: list.width
                spacing: 10
                Repeater {
                    model: panel.routines
                    RoutineRow {
                        required property var modelData
                        routine: modelData
                        onAct: action => panel.command(Wire.routine(modelData.id, action))
                    }
                }
            }
        }
    }
    Rule { anchors.bottom: parent.bottom; width: parent.width }
}
