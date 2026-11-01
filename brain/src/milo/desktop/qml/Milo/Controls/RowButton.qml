import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo

// A whole row that opens something: a task, a meeting, a conversation. Set its `contentItem`; it adds the hover
// wash, the press, the focus ring and the tooltip. `card` gives it its own paper (TaskCard, "Pick up where you
// left off"), whose edge warms to Milo's colour under the pointer.
//
//     RowButton { label: "Open this task"; onClicked: ...; contentItem: RowLayout { ... } }
T.AbstractButton {
    id: row
    property string label: ""
    property string tip: ""
    property bool card: false
    property real radius: card ? Theme.radius.medium : 8
    property real washPadding: card ? 0 : 4

    Layout.fillWidth: true
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitWidth: implicitContentWidth + leftPadding + rightPadding
    implicitHeight: implicitContentHeight + topPadding + bottomPadding
    horizontalPadding: card ? 12 : 0
    verticalPadding: card ? 10 : 0
    scale: pressed ? 0.99 : card && hovered && !Theme.reducedMotion ? 1.005 : 1
    Behavior on scale { Spring { kind: "snappy" } }
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.description: tip
    Keys.onReturnPressed: clicked()

    background: Item {
        Surface {
            anchors.fill: parent
            visible: row.card
            radius: row.radius
            edge: row.hovered ? Tones.fade(Theme.primary, 0.35) : Theme.rule
            lift: row.hovered ? 0.12 : 0.05
            liftRadius: row.hovered ? 8 : 4
            liftY: 2
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: -row.washPadding
            visible: !row.card
            radius: row.radius
            color: Tones.fade(Theme.ink, row.hovered ? 0.04 : 0)
            Behavior on color { ColorSpring { kind: "snappy" } }
            FocusRing { shown: row.visualFocus }
        }
        FocusRing { shown: row.card && row.visualFocus; radius: row.radius + 2 }
    }
    Tip { text: row.tip; shown: row.hovered && row.tip !== "" }
}
