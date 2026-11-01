import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "moods.mjs" as Moods

// Milo's words in the app's rounded face, with a small dot in the colour of his mood. While the words stream in, a
// caret in his colour follows them. Lines with Markdown are laid out as blocks.
RowLayout {
    id: line
    property string text
    property string html
    property var blocks: []
    property string mood: "neutral"
    property bool streaming: false
    readonly property string caret: streaming ? "<font color=\"" + Theme.primary + "\"> ▍</font>" : ""
    spacing: 7

    Item {
        Layout.preferredWidth: 12
        Layout.preferredHeight: 12
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: 4
        Rectangle {
            anchors.centerIn: parent
            width: 7
            height: 7
            radius: 3.5
            color: Moods.color(line.mood, Theme)
            Behavior on color { ColorSpring {} }
        }
        HoverHandler { id: hover }
        Tip { text: "Milo felt " + line.mood; shown: hover.hovered }
    }
    TextEdit {
        visible: line.blocks.length === 0
        Layout.fillWidth: true
        text: line.html + line.caret
        textFormat: TextEdit.RichText
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        color: Theme.ink
        selectionColor: Tones.fade(Theme.primary, 0.35)
        selectedTextColor: Theme.ink
        font.family: Theme.roundedFamily
        font.pixelSize: Theme.type.callout
        Accessible.role: Accessible.StaticText
        Accessible.name: "Milo: " + line.text
    }
    MarkdownText {
        visible: line.blocks.length > 0
        Layout.fillWidth: true
        blocks: line.blocks
        size: Theme.type.callout
        caret: line.caret
    }
}
