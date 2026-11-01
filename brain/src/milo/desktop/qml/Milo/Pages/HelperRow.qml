import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "tasks.mjs" as Tasks

// One helper at work (HelperRow in HelperViews.swift): its mini figure, its task and status, the step it is on, the
// steps before it, how far it is, and Stop while it still runs. A click on the row opens it.
//
// Inputs
//   helper: a `helpers` entry, {id, title, status, step, progress}.
//   steps: its task's steps so far, [{id, kind, title, status}], or [] (Today shows none).
// Outputs
//   open(id), stop(id). The page that holds the row turns them into an action and {"type": "stop_helper", id}.
RowLayout {
    id: row
    property var helper: ({})
    property var steps: []
    signal open(string id)
    signal stop(string id)

    readonly property bool active: Tasks.active(helper.status)
    // The step it is on shows as its own line; the list under it holds the ones before.
    readonly property var earlier: steps.length && steps[steps.length - 1].title === helper.step ? steps.slice(0, -1) : steps

    Layout.fillWidth: true
    spacing: 10
    objectName: "helper-" + helper.id

    RowButton {
        objectName: "open"
        Layout.alignment: Qt.AlignTop
        label: (row.helper.title || "") + ", " + Tasks.helperWords(row.helper.status)
        tip: "Show this in the conversation"
        onClicked: row.open(row.helper.id)
        contentItem: RowLayout {
            spacing: 10
            HelperMini { Layout.alignment: Qt.AlignTop; status: row.helper.status || "working" }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                RowLayout {
                    spacing: 6
                    MiloText {
                        Layout.maximumWidth: implicitWidth
                        Layout.fillWidth: true
                        text: row.helper.title || ""
                        size: 12.5
                        weight: "semibold"
                        rounded: true
                    }
                    MiloText {
                        text: Tasks.helperWords(row.helper.status)
                        size: 10.5
                        weight: "medium"
                        ink: row.helper.status === "needs_you" ? Tones.running : Theme.ink
                        tone: row.helper.status === "needs_you" ? 1 : 0.55
                    }
                    Item { Layout.fillWidth: true }
                }
                MiloText {
                    Layout.fillWidth: true
                    visible: !!row.helper.step
                    text: row.helper.step || ""
                    size: 11.5
                    tone: 0.55
                }
                Repeater {
                    model: row.earlier
                    RowLayout {
                        required property var modelData
                        spacing: 5
                        Icon { name: Tasks.stepIcon(modelData.kind); size: 9; color: Tones.fade(Theme.ink, 0.35); Layout.preferredWidth: 11 }
                        MiloText { Layout.fillWidth: true; text: modelData.title; size: 10.5; tone: 0.35 }
                    }
                }
                ProgressLine {
                    visible: row.active && row.helper.progress !== undefined && row.helper.progress !== null
                    Layout.preferredWidth: 120
                    Layout.topMargin: 2
                    progress: row.helper.progress === undefined ? null : row.helper.progress
                    status: row.helper.status || "working"
                }
            }
        }
    }
    MiloButton {
        objectName: "stop"
        Layout.alignment: Qt.AlignTop
        visible: row.active
        text: "Stop"
        kind: "danger"
        size: "small"
        tip: "Stop this helper"
        Accessible.name: "Stop " + (row.helper.title || "")
        onClicked: row.stop(row.helper.id)
    }
}
