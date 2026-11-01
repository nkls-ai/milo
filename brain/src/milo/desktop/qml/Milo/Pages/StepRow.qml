import QtQuick
import QtQuick.Layouts
import QtQuick.Templates as T
import Milo
import Milo.Controls
import "tasks.mjs" as Tasks

// One step of a task (StepRow in ActivityView.swift): a bead on the thread, what Milo did in plain words, and the raw
// detail when the words are clicked. `step` is an `activity` step, {id, kind, title, detail, status}; `last` ends
// the thread.
Item {
    id: row
    property var step: ({})
    property bool last: false
    property bool showDetail: false

    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + (last ? 0 : 9)
    objectName: "step-" + step.id
    Accessible.role: Accessible.ListItem
    Accessible.name: step.title || ""
    Accessible.description: step.status || ""

    // The thread down to the next bead.
    Rectangle {
        visible: !row.last
        x: 3 + 6.25
        y: 18
        width: 1.5
        height: parent.height - 18
        color: Tones.fade(Theme.primary, 0.25)
    }
    Bead { x: 3; y: 2; status: row.step.status || "running" }

    ColumnLayout {
        id: column
        x: 3 + 14 + 9
        width: parent.width - x
        spacing: 5

        T.AbstractButton {
            id: words
            objectName: "words"
            Layout.fillWidth: true
            enabled: !!row.step.detail
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            implicitHeight: implicitContentHeight
            Accessible.role: Accessible.Button
            Accessible.name: row.step.title || ""
            Keys.onReturnPressed: clicked()
            onClicked: row.showDetail = !row.showDetail
            contentItem: RowLayout {
                spacing: 6
                Icon {
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 2
                    Layout.preferredWidth: 14
                    name: Tasks.stepIcon(row.step.kind)
                    size: 11
                    weight: "medium"
                    color: Tones.fade(Theme.ink, 0.55)
                }
                MiloText {
                    Layout.fillWidth: true
                    text: row.step.title || ""
                    size: 12.5
                    ink: row.step.status === "failed" ? Tones.failed : Theme.ink
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }
            background: Item { FocusRing { shown: words.visualFocus; radius: 6 } }
            Tip { text: "Show what exactly Milo ran"; shown: words.hovered && words.enabled }
        }
        Rectangle {
            Layout.fillWidth: true
            visible: row.showDetail && !!row.step.detail
            implicitHeight: detail.implicitHeight + 16
            radius: 6
            color: Tones.fade(Theme.ink, 0.05)
            TextEdit {
                id: detail
                x: 8
                y: 8
                width: parent.width - 16
                text: row.step.detail || ""
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                font.family: "Consolas, Menlo, DejaVu Sans Mono, monospace"
                font.pixelSize: 11
                color: Tones.fade(Theme.ink, 0.6)
                selectionColor: Tones.fade(Theme.primary, 0.35)
            }
        }
    }
}
