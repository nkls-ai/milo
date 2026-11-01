import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo

// Undo on a finished task (ADR 0026): a small button while it can be undone, then "Undoing…" and "Undone".
// `point` is an undo_points entry: {id, title, state: "ready"|"undoing"|"undone"}. `round` is the small circle on a
// done card. Emits undo(id); the page sends {"type": "undo_task", "id": id}.
Item {
    id: root
    property var point: ({})
    property bool round: false
    signal undo(string id)

    readonly property string state_: point && point.state ? point.state : "ready"
    implicitWidth: loader.implicitWidth
    implicitHeight: loader.implicitHeight

    Loader {
        id: loader
        anchors.centerIn: parent
        sourceComponent: root.state_ !== "ready" ? done : root.round ? roundButton : wordButton
    }

    Component {
        id: wordButton
        T.AbstractButton {
            id: b
            objectName: "undo"  // tests click it as "<row>/undo/undo"
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            text: "Undo"
            horizontalPadding: 9
            verticalPadding: 4
            implicitWidth: implicitContentWidth + leftPadding + rightPadding
            implicitHeight: implicitContentHeight + topPadding + bottomPadding
            scale: pressed ? 0.95 : 1
            Behavior on scale { Spring { kind: "snappy" } }
            Accessible.name: "Undo"
            Accessible.description: "Puts back what Milo changed in this task"
            Keys.onReturnPressed: clicked()
            onClicked: root.undo(root.point.id)
            contentItem: Row {
                spacing: 5
                Icon { anchors.verticalCenter: parent.verticalCenter; name: "arrow.uturn.backward"; size: 11; color: Theme.primary; weight: "bold" }
                MiloText { text: "Undo"; size: 11.5; weight: "semibold"; rounded: true; ink: Theme.primary }
            }
            background: Rectangle {
                radius: 8
                color: Tones.fade(Theme.primary, b.hovered ? 0.16 : 0.09)
                border.color: Tones.fade(Theme.primary, 0.3)
                Behavior on color { ColorSpring { kind: "snappy" } }
                FocusRing { shown: b.visualFocus }
            }
            Tip { text: "Put back what Milo changed in “" + (root.point.title || "") + "”"; shown: b.hovered }
        }
    }

    Component {
        id: roundButton
        T.AbstractButton {
            id: r
            objectName: "undo"
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            implicitWidth: 24
            implicitHeight: 24
            scale: pressed ? 0.96 : 1
            Behavior on scale { Spring { kind: "snappy" } }
            Accessible.name: "Undo"
            Accessible.description: "Takes back what Milo just did"
            Keys.onReturnPressed: clicked()
            onClicked: root.undo(root.point.id)
            background: Rectangle {
                radius: width / 2
                color: Tones.fade(Theme.primary, r.hovered ? 0.2 : 0.1)
                border.color: Tones.fade(Theme.primary, 0.28)
                Behavior on color { ColorSpring { kind: "snappy" } }
                FocusRing { shown: r.visualFocus }
            }
            contentItem: Item {
                Icon { anchors.centerIn: parent; name: "arrow.uturn.backward"; size: 12; color: Theme.primary; weight: "bold" }
            }
            Tip { text: "Undo “" + (root.point.title || "") + "”"; shown: r.hovered }
        }
    }

    Component {
        id: done
        Row {
            spacing: 5
            Accessible.role: Accessible.StaticText
            Accessible.name: root.state_ === "undoing" ? "Undoing" : "Undone: Milo put back what this task changed"
            Spinner { visible: root.state_ === "undoing" && root.round; size: 14; anchors.verticalCenter: parent.verticalCenter }
            Icon {
                visible: !(root.state_ === "undoing" && root.round)
                anchors.verticalCenter: parent.verticalCenter
                name: "arrow.uturn.backward"
                size: root.round ? 15 : 11
                color: Tones.fade(Theme.ink, root.round ? 0.4 : 0.55)
                weight: "medium"
            }
            MiloText {
                visible: !root.round
                text: root.state_ === "undoing" ? "Undoing…" : "Undone"
                size: 11.5
                weight: "medium"
                rounded: true
                tone: root.state_ === "undoing" ? 0.55 : 0.5
            }
        }
    }
}
