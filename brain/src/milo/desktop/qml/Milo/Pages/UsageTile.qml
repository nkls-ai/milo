import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// One headline number on the Usage page: big value, what it counts, and one quiet line of context (StatTile).
Surface {
    id: tile
    property string value
    property string label
    property string note
    property string icon
    property color tint: Theme.primary

    radius: 16
    lift: 0.06
    liftRadius: 10
    liftY: 3
    Layout.fillWidth: true
    Layout.minimumWidth: 140
    implicitHeight: column.implicitHeight + 24
    Accessible.role: Accessible.StaticText
    Accessible.name: label + ": " + value + ", " + note

    ColumnLayout {
        id: column
        x: 14
        y: 12
        width: tile.width - 28
        spacing: 4
        RowLayout {
            spacing: 6
            Rectangle {
                implicitWidth: 20
                implicitHeight: 20
                radius: 10
                color: Tones.fade(tile.tint, 0.15)
                Icon { anchors.centerIn: parent; name: tile.icon; size: 11; color: tile.tint; weight: "bold" }
            }
            MiloText { Layout.fillWidth: true; text: tile.label; size: 11.5; weight: "semibold"; rounded: true; tone: 0.62 }
        }
        MiloText {
            Layout.fillWidth: true
            text: tile.value
            size: 26
            weight: "bold"
            rounded: true
            tabular: true
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: 18
        }
        MiloText { Layout.fillWidth: true; text: tile.note; size: 11; tone: 0.5 }
    }
}
