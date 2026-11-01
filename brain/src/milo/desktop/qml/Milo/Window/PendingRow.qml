import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// "Listening…" or "Thinking…" at the end of the thread while nothing has arrived yet.
Item {
    id: row
    property string text
    property bool listening: false
    property real topPadding: 0
    implicitHeight: text === "" ? 0 : line.implicitHeight + topPadding
    visible: text !== ""

    RowLayout {
        id: line
        y: row.topPadding
        spacing: 10
        Item { implicitWidth: 46; implicitHeight: 1 }
        ThinkingDots {
            dot: 4.5
            color: row.listening ? Theme.primary : Theme.accent
            Layout.alignment: Qt.AlignVCenter
        }
        MiloText { text: row.text; size: 12.5; rounded: true; tone: 0.55 }
    }
}
