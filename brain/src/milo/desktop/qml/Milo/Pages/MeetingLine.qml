import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "format.mjs" as Format

// One line of a meeting's transcript (LineRow): the time into the meeting, the speaker's name when they change, the
// words beside a bar in their colour. `line` is a meeting_lines entry {at, end, who, me, text}.
Item {
    id: row
    property var line: ({})
    property bool named: true
    property color tint: Theme.primary

    implicitHeight: content.implicitHeight + (named ? 12 : 4)
    Accessible.role: Accessible.StaticText
    Accessible.name: line.who + " at " + Format.clock(line.at) + ": " + line.text

    RowLayout {
        id: content
        y: row.named ? 12 : 4
        width: row.width
        spacing: 12
        MiloText {
            Layout.preferredWidth: 44
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: row.named ? 1 : 2.5
            text: Format.clock(row.line.at)
            size: 11
            tone: 0.4
            tabular: true
            horizontalAlignment: Text.AlignRight
        }
        Item {
            Layout.fillWidth: true
            implicitHeight: words.implicitHeight
            Rectangle {
                width: 2.5
                height: parent.height
                radius: 1.25
                color: Tones.fade(row.tint, 0.5)
            }
            ColumnLayout {
                id: words
                x: 10
                width: parent.width - 10
                spacing: 2
                MiloText {
                    id: nameLabel
                    visible: row.named
                    text: row.line.who || ""
                    size: 12
                    weight: "semibold"
                    rounded: true
                    ink: row.tint
                }
                TextEdit {
                    Layout.fillWidth: true
                    text: row.line.text || ""
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: Tones.fade(Theme.ink, 0.9)
                    selectionColor: Tones.fade(Theme.primary, 0.35)
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.type.body  // 13.5 on the Mac; pixel sizes are whole
                }
            }
        }
    }
}
