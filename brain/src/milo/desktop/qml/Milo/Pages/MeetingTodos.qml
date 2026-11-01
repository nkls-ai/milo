import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// The to-dos from a meeting (TodoList), the user's own first, each with "Add to Reminders". Emits add(index), and
// add(-1) for all of the user's.
MiloScrollView {
    id: list
    property var notes: ({})
    signal add(int index)

    readonly property var todos: notes.todos || []
    // The user's own first, otherwise in the notes' order; each keeps its index in the notes.
    readonly property var order: todos.map((t, i) => i).sort((a, b) =>
        todos[a].mine !== todos[b].mine ? (todos[a].mine ? -1 : 1) : a - b)

    leftPadding: 22
    rightPadding: 22
    topPadding: 18
    bottomPadding: 18
    maxContentWidth: 680
    spacing: 10

    MiloText {
        visible: list.todos.length === 0
        text: "Nobody took on anything in this one."
        tone: 0.55
    }
    MiloButton {
        objectName: "addAll"
        visible: !!list.notes.reminders && list.todos.filter(t => t.mine && !t.added).length > 1
        text: "Add all of mine to Reminders"
        onClicked: list.add(-1)
    }
    Repeater {
        model: list.order
        Rectangle {
            id: row
            required property int modelData
            readonly property var todo: list.todos[modelData]
            readonly property string who: todo.mine ? "You" : todo.owner || "Nobody yet"
            objectName: "todo-" + modelData
            Layout.fillWidth: true
            implicitHeight: line.implicitHeight + 24
            radius: Theme.radius.medium
            color: Theme.card
            border.color: Theme.rule
            Accessible.role: Accessible.Grouping
            Accessible.name: todo.text

            RowLayout {
                id: line
                anchors.fill: parent
                anchors.margins: 12
                spacing: 12
                Icon {
                    name: row.todo.added ? "checkmark.circle" : "circle"
                    size: 17
                    weight: "medium"
                    color: row.todo.added ? Theme.primary : Tones.fade(Theme.ink, 0.35)
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2
                    MiloText {
                        Layout.fillWidth: true
                        text: row.todo.text
                        size: 13.5
                        weight: "medium"
                        wrapMode: Text.WordWrap
                    }
                    MiloText {
                        text: row.todo.due ? row.who + " · " + row.todo.due : row.who
                        size: 11.5
                        ink: row.todo.mine ? Theme.primary : Theme.ink
                        tone: row.todo.mine ? 1 : 0.55
                    }
                }
                MiloText {
                    visible: !!row.todo.added
                    text: "In Reminders"
                    size: 12
                    weight: "medium"
                    rounded: true
                    tone: 0.5
                }
                MiloButton {
                    objectName: "add"
                    visible: !row.todo.added && !!list.notes.reminders
                    text: "Add to Reminders"
                    kind: "quiet"
                    onClicked: list.add(row.modelData)
                }
            }
        }
    }
}
