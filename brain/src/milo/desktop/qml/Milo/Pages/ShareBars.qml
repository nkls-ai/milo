import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Each row's share of the largest, as a thin bar under its label and value. `rows` are [{label, value, shown}].
ColumnLayout {
    id: bars
    property var rows: []
    property color tint: Theme.primary
    readonly property real most: Math.max(1, ...rows.map(r => r.value))

    Layout.fillWidth: true
    spacing: 9

    Repeater {
        model: bars.rows
        ColumnLayout {
            required property var modelData
            Layout.fillWidth: true
            spacing: 4
            Accessible.role: Accessible.StaticText
            Accessible.name: modelData.label + ": " + modelData.shown
            RowLayout {
                MiloText { Layout.fillWidth: true; text: modelData.label; size: 12.5; weight: "medium"; rounded: true }
                MiloText { text: modelData.shown; size: 11.5; tone: 0.55; tabular: true }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 5
                radius: 2.5
                color: Tones.fade(Theme.ink, 0.06)
                Rectangle {
                    height: parent.height
                    radius: 2.5
                    width: Math.max(4, parent.width * modelData.value / bars.most)
                    color: bars.tint
                    Behavior on width { Spring { kind: "gentle" } }
                }
            }
        }
    }
}
