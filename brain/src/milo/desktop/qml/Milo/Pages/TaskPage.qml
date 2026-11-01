import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "format.mjs" as Format
import "tasks.mjs" as Tasks

// A task's own page (TaskPage.swift): what it is, how it went, every step, the result and the files it touched.
//
// Inputs
//   entry: a `task` history entry, {id, ts, text, title, status: "running"|"done"|"failed", result, steps, files}.
//   conversation: the `conversations` info it was asked in, {id, title, …}, or null.
//   helper: the `helpers` entry working on it, or null.
//   undoPoint: its `undo_points` entry, or null.
//   now: the clock for "Today at 9:12".
// Outputs
//   command({"type": "stop_helper", id}), command({"type": "undo_task", id});
//   action("openConversation", conversation id), action("reveal", file path).
Item {
    id: page
    property var entry: ({})
    property var conversation: null
    property var helper: null
    property var undoPoint: null
    property var now: new Date()
    // `now` as a Date; a sample may give it as "2026-10-30T16:20".
    readonly property var clock: typeof now === "string" ? Format.parse(now) : now
    signal command(var message)
    signal action(string name, var value)

    readonly property bool running: entry.status === "running"
    readonly property bool needsYou: !!helper && helper.status === "needs_you"
    readonly property var steps: entry.steps || []
    readonly property var files: entry.files || []
    readonly property var date: Format.parse(entry.ts)

    MiloScrollView {
        anchors.fill: parent
        leftPadding: 26
        rightPadding: 26
        topPadding: 20
        bottomPadding: 28
        maxContentWidth: 640
        spacing: 18

        // ---- the header
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 10

            MiloButton {
                objectName: "conversation"
                visible: !!page.conversation
                kind: "plain"
                size: "small"
                iconName: "bubble.left"
                text: page.conversation ? "Asked in “" + page.conversation.title + "”" : ""
                tip: "Open the conversation this task came from"
                onClicked: page.action("openConversation", page.conversation.id)
            }
            RowLayout {
                spacing: 12
                StatusSeal { status: page.entry.status || "running"; needsYou: page.needsYou; size: 34 }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    MiloText {
                        Layout.fillWidth: true
                        text: Tasks.headline(page.entry)
                        size: 19
                        weight: "bold"
                        rounded: true
                        wrapMode: Text.WordWrap
                        Accessible.role: Accessible.Heading
                    }
                    RowLayout {
                        spacing: 6
                        Pill {
                            text: page.needsYou ? "Waiting for you" : Tasks.statusHeadline(page.entry.status)
                            tint: page.needsYou ? Theme.think : Tones.status(page.entry.status)
                        }
                        MiloText {
                            visible: !!page.date
                            text: page.date ? Format.at(page.date, page.clock) : ""
                            size: 11.5
                            tone: 0.5
                            tabular: true
                        }
                    }
                }
                MiloButton {
                    objectName: "stop"
                    visible: page.running
                    text: "Stop"
                    kind: "danger"
                    tip: "Stop this helper"
                    onClicked: page.command({ type: "stop_helper", id: page.entry.id })
                }
                UndoButton {
                    objectName: "undo"
                    visible: !page.running && !!page.undoPoint
                    point: page.undoPoint || ({})
                    onUndo: id => page.command({ type: "undo_task", id: id })
                }
            }
            TextEdit {
                Layout.fillWidth: true
                visible: !!page.entry.text && page.entry.text !== Tasks.headline(page.entry)
                text: page.entry.text || ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                font.family: Theme.fontFamily
                font.pixelSize: 12  // 12.5 on the Mac; pixel sizes are whole
                color: Tones.fade(Theme.ink, 0.65)
                selectionColor: Tones.fade(Theme.primary, 0.35)
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.topMargin: 2
                visible: page.running && !!page.helper
                spacing: 5
                MiloText {
                    visible: !!page.helper && !!page.helper.step
                    text: page.helper ? page.helper.step || "" : ""
                    size: 12
                    weight: "medium"
                    tone: 0.75
                }
                ProgressLine {
                    Layout.fillWidth: true
                    implicitHeight: 4
                    progress: page.helper && page.helper.progress !== undefined ? page.helper.progress : null
                    status: page.helper ? page.helper.status : "working"
                }
            }
        }

        // ---- the result, with a stripe in its status colour
        Rectangle {
            Layout.fillWidth: true
            visible: !!page.entry.result && !page.running
            implicitHeight: result.implicitHeight + 28
            radius: 14
            color: Theme.card
            border.color: Theme.rule
            clip: true
            Accessible.role: Accessible.StaticText
            Accessible.name: "Milo reported: " + (page.entry.result || "")
            Rectangle { width: 4; height: parent.height; color: Tones.status(page.entry.status) }
            TextEdit {
                id: result
                x: 18
                y: 14
                width: parent.width - 32
                text: page.entry.result || ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                font.family: Theme.roundedFamily
                font.pixelSize: Theme.type.callout
                color: Theme.ink
                selectionColor: Tones.fade(Theme.primary, 0.35)
            }
        }

        // ---- the files
        ColumnLayout {
            Layout.fillWidth: true
            visible: page.files.length > 0
            spacing: 8
            SectionHeader { text: page.files.length === 1 ? "1 file" : page.files.length + " files" }
            Surface {
                Layout.fillWidth: true
                implicitHeight: fileList.implicitHeight
                radius: Theme.radius.medium
                lift: 0
                ColumnLayout {
                    id: fileList
                    width: parent.width
                    spacing: 0
                    Repeater {
                        model: page.files
                        ColumnLayout {
                            required property string modelData
                            required property int index
                            Layout.fillWidth: true
                            spacing: 0
                            FileRow { path: modelData; onReveal: page.action("reveal", modelData) }
                            Rule { visible: index < page.files.length - 1; Layout.leftMargin: 40 }
                        }
                    }
                }
            }
        }

        // ---- the steps
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 8
            SectionHeader { text: page.steps.length === 0 ? "No steps yet" : Tasks.steps(page.steps.length) }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 0
                Repeater {
                    model: page.steps
                    StepRow {
                        required property var modelData
                        required property int index
                        step: modelData
                        last: index === page.steps.length - 1
                    }
                }
            }
        }
    }
}
