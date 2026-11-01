import QtQuick
import QtQuick.Layouts
import Milo

// A section on a card with a small coloured heading: Today's "Reminders", Usage's "Day by day" (TodayCard).
Surface {
    id: card
    default property alias content: rows.data
    property string title
    property string icon
    property color tint: Theme.primary
    property alias spacing: rows.spacing

    radius: 16
    lift: 0.06
    liftRadius: 10
    liftY: 3
    implicitWidth: column.implicitWidth + 28
    implicitHeight: column.implicitHeight + 24
    Layout.fillWidth: true
    Accessible.role: Accessible.Grouping
    Accessible.name: title

    ColumnLayout {
        id: column
        x: 14
        y: 12
        width: card.width - 28
        spacing: 10

        RowLayout {
            spacing: 7
            Rectangle {
                implicitWidth: 20
                implicitHeight: 20
                radius: 10
                color: Tones.fade(card.tint, 0.15)
                Icon { anchors.centerIn: parent; name: card.icon; size: 11; color: card.tint; weight: "bold" }
            }
            MiloText { text: card.title; size: 12; weight: "bold"; rounded: true; tone: 0.7 }
        }
        ColumnLayout {
            id: rows
            Layout.fillWidth: true
            spacing: 10
        }
    }
}
