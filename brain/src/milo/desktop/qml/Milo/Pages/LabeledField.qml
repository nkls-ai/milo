import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// A field with its name above it, for a short form.
ColumnLayout {
    id: labeled
    property string label
    property alias text: field.text
    property alias placeholder: field.placeholder
    // Enter, or leaving the field: the time to look the address up again.
    signal editingDone()

    Layout.fillWidth: true
    spacing: 4
    MiloText { text: labeled.label; size: Theme.type.caption; weight: "medium"; tone: 0.7 }
    MiloField {
        id: field
        objectName: "field"
        Layout.fillWidth: true
        onAccepted: labeled.editingDone()
        onActiveFocusChanged: if (!activeFocus) labeled.editingDone()
    }
}
