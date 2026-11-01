import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// Markdown blocks laid out in Milo's type (MarkdownView): headings in his rounded face, bullets as small dots, to-dos
// as boxes, quotes with a bar, code on a faint wash. `blocks` come from presentation/markdown.parse, their `html`
// already escaped. `caret` goes after the last block while the words still stream in.
Column {
    id: md
    property var blocks: []
    property real size: Theme.type.body + 0.5
    property string caret: ""

    Repeater {
        model: md.blocks
        delegate: Item {
            id: block
            required property var modelData
            required property int index
            readonly property string html: modelData.html + (index === md.blocks.length - 1 ? md.caret : "")
            width: md.width
            implicitHeight: body.implicitHeight + modelData.gap
            height: implicitHeight

            Loader {
                id: body
                y: block.modelData.gap
                width: parent.width
                sourceComponent: ({ heading: heading, rule: rule, code: code, quote: quote, bullet: listItem, numbered: listItem,
                                    todo: listItem })[block.modelData.kind] || prose
            }

            Component {
                id: prose
                Prose { html: block.html }
            }
            Component {
                id: heading
                Prose {
                    html: block.html
                    size: block.modelData.level === 1 ? md.size + 8 : block.modelData.level === 2 ? md.size + 2.5 : md.size + 0.5
                    bold: true
                    Accessible.role: Accessible.Heading
                }
            }
            Component {
                id: rule
                Item { implicitHeight: 9; Rule { anchors.verticalCenter: parent.verticalCenter; width: parent.width } }
            }
            Component {
                id: code
                Rectangle {
                    implicitHeight: codeText.implicitHeight + 20
                    radius: 8
                    color: Tones.fade(Theme.ink, 0.05)
                    TextEdit {
                        id: codeText
                        x: 10
                        y: 10
                        width: parent.width - 20
                        text: block.modelData.text
                        textFormat: TextEdit.PlainText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        color: Tones.fade(Theme.ink, 0.85)
                        font.family: "Consolas, Cascadia Mono, DejaVu Sans Mono, monospace"
                        font.pixelSize: md.size - 1.5
                    }
                }
            }
            Component {
                id: quote
                Item {
                    implicitHeight: quoteText.implicitHeight
                    Rectangle { width: 3; height: parent.height; radius: 1.5; color: Tones.fade(Theme.primary, 0.35) }
                    Prose { id: quoteText; x: 12; width: parent.width - 12; html: block.html }
                }
            }
            Component {
                id: listItem
                // A list item: its mark in a fixed column on the first line, the words wrapping beside it.
                RowLayout {
                    spacing: 8
                    Item {
                        Layout.leftMargin: block.modelData.depth * 20
                        Layout.preferredWidth: 16
                        Layout.preferredHeight: md.size * 1.35
                        Layout.alignment: Qt.AlignTop
                        Rectangle {
                            visible: block.modelData.kind === "bullet"
                            anchors.centerIn: parent
                            width: 5; height: 5; radius: 2.5
                            color: Tones.fade(Theme.primary, 0.7)
                        }
                        MiloText {
                            visible: block.modelData.kind === "numbered"
                            anchors.centerIn: parent
                            text: block.modelData.number + "."
                            size: md.size
                            weight: "semibold"
                            rounded: true
                            tabular: true
                            ink: Theme.primary
                        }
                        Icon {
                            visible: block.modelData.kind === "todo"
                            anchors.centerIn: parent
                            name: block.modelData.done ? "checkmark.circle" : "circle"
                            size: md.size
                            color: block.modelData.done ? Theme.primary : Tones.fade(Theme.ink, 0.5)
                        }
                    }
                    Prose {
                        Layout.fillWidth: true
                        html: block.html
                        opacity: block.modelData.done ? 0.6 : 1
                    }
                }
            }
        }
    }

    component Prose: TextEdit {
        property string html
        property real size: md.size
        property bool bold: false
        text: html
        textFormat: TextEdit.RichText
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.Wrap
        color: bold ? Theme.ink : Tones.fade(Theme.ink, 0.92)
        selectionColor: Tones.fade(Theme.primary, 0.35)
        selectedTextColor: Theme.ink
        font.family: bold ? Theme.roundedFamily : Theme.fontFamily
        font.pixelSize: size
        font.weight: bold ? Theme.type.weights.bold : Theme.type.weights.regular
        onLinkActivated: function(link) { Qt.openUrlExternally(link) }
    }
}
