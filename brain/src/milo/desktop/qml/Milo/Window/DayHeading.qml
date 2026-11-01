import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// "Today", "Yesterday" or a date over the thread, with a hairline to the edge.
Item {
    id: heading
    property string text
    property real gutter: 46
    property real bottomPadding: 0
    implicitHeight: label.implicitHeight + bottomPadding

    RowLayout {
        width: parent.width - heading.gutter - 10
        x: heading.gutter + 10
        spacing: 10
        MiloText { id: label; text: heading.text; size: 11; weight: "semibold"; rounded: true; tone: 0.5 }
        Rule { Layout.alignment: Qt.AlignVCenter }
    }
}
