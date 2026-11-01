import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Dictation that couldn't go into a field, kept here so nothing said is lost: Copy, or let it go.
Item {
    id: kept
    readonly property bool shown: shell.kept.text !== undefined && shell.kept.text !== ""
    property bool copied: false
    implicitHeight: shown ? card.implicitHeight + Theme.space.s : 0
    height: implicitHeight
    clip: true
    Behavior on height { Spring {} }

    Card {
        id: card
        x: Theme.space.l
        width: kept.width - 2 * Theme.space.l
        opacity: kept.shown ? 1 : 0
        Behavior on opacity { Spring {} }
        spacing: Theme.space.s

        CardHeading { icon: "mic"; title: "Your dictated text" }
        MiloText {
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            maximumLineCount: 5
            elide: Text.ElideRight
            text: shell.kept.text || ""
            size: Theme.type.body
        }
        RowLayout {
            spacing: Theme.space.s
            MiloButton {
                kind: "primary"
                size: "small"
                iconName: kept.copied ? "check" : "doc.on.doc"
                text: kept.copied ? "Copied" : "Copy text"
                onClicked: { shell.copy(shell.kept.text); kept.copied = true }
            }
            MiloButton { kind: "quiet"; size: "small"; text: "Dismiss"; onClicked: { kept.copied = false; shell.dismissKept() } }
        }
    }
}
