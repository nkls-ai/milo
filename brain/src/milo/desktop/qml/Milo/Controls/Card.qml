import QtQuick
import QtQuick.Layouts
import Milo

// A soft card on the window's tinted paper (ThemedCard). Its children stack in a column, full width; the card is as
// tall as they are plus `padding`.
//
//     Card { CardHeading { icon: "mic"; title: "Dictation" }  ChoiceList { ... } }
Surface {
    id: card
    default property alias content: column.data
    property real padding: Theme.space.l
    property alias spacing: column.spacing

    implicitWidth: column.implicitWidth + 2 * padding
    implicitHeight: column.implicitHeight + 2 * padding
    Layout.fillWidth: true

    ColumnLayout {
        id: column
        x: card.padding
        y: card.padding
        width: card.width - 2 * card.padding
        spacing: Theme.space.m - 2
    }
}
