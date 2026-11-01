import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// What the user said, quieter than Milo, with how it was said: spoken, typed or from the phone.
RowLayout {
    id: line
    property string text
    property string icon: "mic"
    property string help: "You said this"
    spacing: 7

    Item {
        Layout.preferredWidth: 12
        Layout.preferredHeight: 12
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: 3
        Icon { anchors.centerIn: parent; name: line.icon; size: 10.5; color: Tones.fade(Theme.ink, 0.5); weight: "medium" }
        HoverHandler { id: hover }
        Tip { text: line.help; shown: hover.hovered }
    }
    TextEdit {
        Layout.fillWidth: true
        text: line.text
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        textFormat: TextEdit.PlainText
        color: Tones.fade(Theme.ink, 0.62)
        selectionColor: Tones.fade(Theme.primary, 0.35)
        selectedTextColor: Theme.ink
        font.family: Theme.fontFamily
        font.pixelSize: Theme.type.body
    }
}
