import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "tasks.mjs" as Tasks

// A task in the chat (TaskCard in TaskPage.swift): one compact card with what it is, how it's going and how many
// steps. A click opens its page.
//
// Inputs
//   entry: a `task` history entry, {id, text, title, status: "running"|"done"|"failed", result, steps, files}.
//   helper: the `helpers` entry working on it, or null.
//   undoPoint: its `undo_points` entry once it changed something and finished, or null.
// Outputs
//   command({"type": "undo_task", id}); action("openTask", {id, conversation}).
Item {
    id: card
    property var entry: ({})
    property var helper: null
    property var undoPoint: null
    signal command(var message)
    signal action(string name, var value)

    Layout.fillWidth: true
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    objectName: "task-" + entry.id

    RowButton {
        id: button
        objectName: "open"
        anchors.fill: parent
        card: true
        label: "Task: " + Tasks.headline(card.entry) + ", " + Tasks.statusWords(card.entry.status)
        tip: "Open this task"
        Accessible.description: "Opens its steps and result"
        onClicked: card.action("openTask", { id: card.entry.id, conversation: card.entry.conversation || "" })
        contentItem: RowLayout {
            spacing: 11
            StatusSeal { status: card.entry.status || "running"; needsYou: !!card.helper && card.helper.status === "needs_you" }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                MiloText { Layout.fillWidth: true; text: Tasks.headline(card.entry); weight: "semibold"; rounded: true }
                MiloText {
                    Layout.fillWidth: true
                    text: Tasks.line(card.entry, card.helper)
                    size: 11.5
                    ink: card.entry.status === "failed" ? Tones.failed : Theme.ink
                    tone: card.entry.status === "failed" ? 1 : 0.58
                }
                ProgressLine {
                    Layout.fillWidth: true
                    Layout.topMargin: 3
                    visible: card.entry.status === "running"
                    progress: card.helper && card.helper.progress !== undefined ? card.helper.progress : null
                    status: card.helper ? card.helper.status : "working"
                }
            }
            // Room for the Undo laid over the card.
            Item { visible: !!card.undoPoint; implicitWidth: 76 }
            Icon {
                name: "chevron.right"
                size: 10
                weight: "bold"
                color: Tones.fade(Theme.ink, button.hovered ? 0.6 : 0.3)
                Layout.leftMargin: button.hovered && !Theme.reducedMotion ? 2 : 0
            }
        }
    }
    // Over the card, not in it: a button inside the card's own button would open the task instead.
    UndoButton {
        objectName: "undo"
        visible: !!card.undoPoint
        anchors.right: parent.right
        anchors.rightMargin: 30
        anchors.verticalCenter: parent.verticalCenter
        point: card.undoPoint || ({})
        onUndo: id => card.command({ type: "undo_task", id: id })
    }
}
