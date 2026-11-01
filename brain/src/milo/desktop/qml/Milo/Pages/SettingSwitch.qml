import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// A setting that is on or off: its words on the left, a switch on the right. The switch shows the brain's value
// and only asks for the change (changed(!on)); it moves when the brain's next `settings` report says so.
RowLayout {
    id: row
    property string title
    property string detail
    property string icon: ""  // with an icon it is a card's heading (CardHeading), without one a row inside a card
    property bool on: true
    signal changed(bool on)

    Layout.fillWidth: true
    spacing: 12

    CardHeading {
        visible: row.icon !== ""
        icon: row.icon
        title: row.title
        detail: row.detail
    }
    ColumnLayout {
        visible: row.icon === ""
        Layout.fillWidth: true
        spacing: 2
        MiloText { Layout.fillWidth: true; text: row.title; wrapMode: Text.WordWrap }
        MiloText { Layout.fillWidth: true; visible: row.detail !== ""; text: row.detail; size: 11; tone: 0.65; wrapMode: Text.WordWrap }
    }
    MiloToggle {
        objectName: "switch"
        Layout.alignment: Qt.AlignVCenter
        text: row.title
        checkable: false
        checked: row.on
        onClicked: row.changed(!row.on)
    }
}
