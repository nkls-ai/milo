import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "meeting.mjs" as Meeting

// A meeting's notes laid out like the Mac's MarkdownView: headings in Milo's rounded face, bullets as small dots,
// to-dos as rings, quotes with a bar. A click on a link emits link(url); the page decides what may open.
Column {
    id: notes
    property string markdown: ""
    property real size: Theme.type.body + 0.5
    signal link(string url)

    Layout.fillWidth: true
    Repeater {
        model: Meeting.blocks(notes.markdown)
        Item {
            id: block
            required property var modelData
            width: notes.width
            implicitHeight: body.implicitHeight + modelData.gap

            RowLayout {
                id: body
                y: block.modelData.gap
                width: parent.width
                spacing: 8
                readonly property bool listItem: ["bullet", "numbered", "todo"].indexOf(block.modelData.kind) >= 0

                Item {
                    visible: body.listItem
                    Layout.leftMargin: (block.modelData.depth || 0) * 20
                    Layout.preferredWidth: 16
                    Layout.preferredHeight: notes.size * 1.6
                    Layout.alignment: Qt.AlignTop
                    Rectangle {
                        visible: block.modelData.kind === "bullet"
                        anchors.centerIn: parent
                        width: 5
                        height: 5
                        radius: 2.5
                        color: Tones.fade(Theme.primary, 0.7)
                    }
                    MiloText {
                        visible: block.modelData.kind === "numbered"
                        anchors.centerIn: parent
                        text: block.modelData.number + "."
                        size: notes.size
                        weight: "semibold"
                        rounded: true
                        tabular: true
                        ink: Theme.primary
                    }
                    Icon {
                        visible: block.modelData.kind === "todo"
                        anchors.centerIn: parent
                        name: block.modelData.done ? "checkmark.circle" : "circle"
                        size: notes.size
                        color: block.modelData.done ? Theme.primary : Tones.fade(Theme.ink, 0.5)
                    }
                }
                Rectangle {
                    visible: block.modelData.kind === "quote"
                    Layout.preferredWidth: 3
                    Layout.fillHeight: true
                    radius: 1.5
                    color: Tones.fade(Theme.primary, 0.35)
                }
                Rule { visible: block.modelData.kind === "rule"; Layout.topMargin: 4; Layout.bottomMargin: 4 }
                TextEdit {
                    readonly property bool heading: block.modelData.kind === "heading"
                    readonly property int level: block.modelData.level || 0
                    visible: block.modelData.kind !== "rule"
                    Layout.fillWidth: true
                    Layout.leftMargin: block.modelData.kind === "quote" ? 9 : 0
                    text: block.modelData.html || ""
                    textFormat: TextEdit.RichText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    opacity: block.modelData.done ? 0.6 : 1
                    color: heading ? Theme.ink : Tones.fade(Theme.ink, 0.92)
                    selectionColor: Tones.fade(Theme.primary, 0.35)
                    selectedTextColor: Theme.ink
                    font.family: heading ? Theme.roundedFamily : Theme.fontFamily
                    font.pixelSize: !heading ? notes.size : level === 1 ? notes.size + 8 : level === 2 ? notes.size + 2.5 : notes.size + 0.5
                    font.weight: !heading ? Theme.type.weights.regular : level <= 2 ? Theme.type.weights.bold : Theme.type.weights.semibold
                    Accessible.role: heading ? Accessible.Heading : Accessible.StaticText
                    onLinkActivated: url => notes.link(url)
                    HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor }
                }
            }
        }
    }
}
