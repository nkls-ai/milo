import QtQuick
import QtQuick.Layouts
import Milo

// A heading over a card: a small icon in Milo's colour, a title, and a line in plain words.
RowLayout {
    id: heading
    property string icon
    property string title
    property string detail

    spacing: Theme.space.s
    Layout.fillWidth: true

    Icon {
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: 1
        Layout.preferredWidth: 18
        name: heading.icon
        size: 14
        color: Theme.primary
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        MiloText {
            Layout.fillWidth: true
            text: heading.title
            size: Theme.type.callout
            weight: "semibold"
            rounded: true
            wrapMode: Text.WordWrap
        }
        MiloText {
            Layout.fillWidth: true
            visible: heading.detail !== ""
            text: heading.detail
            size: Theme.type.caption
            tone: 0.6
            wrapMode: Text.WordWrap
        }
    }
}
