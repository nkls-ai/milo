import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Text Milo wrote for the user (ADR 0033), as he wrote it, with a button that copies it: it may have gone into their
// field, or be waiting here because it couldn't.
Item {
    id: block
    property string text
    property bool copied: false
    implicitHeight: card.implicitHeight

    Card {
        id: card
        x: 19  // under Milo's words, past his dot
        width: block.width - x
        radius: Theme.radius.medium
        padding: Theme.space.m
        lift: 0
        spacing: Theme.space.s

        TextEdit {
            Layout.fillWidth: true
            text: block.text
            textFormat: TextEdit.PlainText
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: Theme.ink
            selectionColor: Tones.fade(Theme.primary, 0.35)
            selectedTextColor: Theme.ink
            font.family: Theme.fontFamily
            font.pixelSize: Theme.type.body + 0.5
            Accessible.name: "Text Milo wrote"
        }
        MiloButton {
            kind: "plain"
            size: "small"
            iconName: block.copied ? "check" : "doc.on.doc"
            text: block.copied ? "Copied" : "Copy"
            tip: "Copies the text, to paste it yourself"
            onClicked: { shell.copy(block.text); block.copied = true; reset.restart() }
        }
    }
    Timer { id: reset; interval: 1500; onTriggered: block.copied = false }
}
