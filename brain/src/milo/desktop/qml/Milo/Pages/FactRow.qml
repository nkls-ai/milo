import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// One fact (FactRow in KnowledgeView.swift). Edit turns it into a field; Forget asks once more, in the row.
Rectangle {
    id: row
    property var fact: ({})
    signal forget()
    signal edit(string text)

    property bool editing: false
    property bool asking: false

    Layout.fillWidth: true
    implicitHeight: content.implicitHeight + 12
    radius: 9
    color: Tones.fade(Theme.ink, 0.05)
    objectName: "fact-" + fact.id

    function save() {
        const text = field.text.trim()
        editing = false
        if (text !== "" && text !== fact.text) edit(text)
    }

    HoverHandler { id: hover }

    ColumnLayout {
        id: content
        x: 10
        y: 6
        width: parent.width - 20
        spacing: 8

        RowLayout {
            visible: !row.editing
            spacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                MiloText {
                    Layout.fillWidth: true
                    text: row.fact.text || ""
                    wrapMode: Text.WordWrap
                }
                MiloText {
                    visible: !!row.fact.pinned
                    text: "Always in mind"
                    size: 10.5
                    weight: "medium"
                    ink: Theme.primary
                    Tip { text: "Milo has this in mind in every conversation."; shown: pinHover.hovered }
                    HoverHandler { id: pinHover }
                }
            }
            Row {
                Layout.alignment: Qt.AlignTop
                spacing: 10
                opacity: hover.hovered || row.asking || editButton.activeFocus || forgetButton.activeFocus ? 1 : 0.35
                Behavior on opacity { Spring { kind: "snappy" } }
                MiloButton {
                    id: editButton
                    objectName: "edit"
                    text: "Edit"
                    kind: "plain"
                    size: "small"
                    onClicked: { field.text = row.fact.text; row.editing = true; field.focusAndSelect() }
                }
                MiloButton {
                    id: forgetButton
                    objectName: "forget"
                    text: "Forget"
                    kind: "plain"
                    size: "small"
                    onClicked: row.asking = true
                }
            }
        }

        RowLayout {
            visible: row.editing
            spacing: 8
            MiloField {
                id: field
                objectName: "field"
                Layout.fillWidth: true
                multiline: true
                placeholder: "What Milo should know"
                onAccepted: row.save()
                onCancelled: row.editing = false
            }
            MiloButton { objectName: "save"; text: "Save"; kind: "primary"; size: "small"; onClicked: row.save() }
            MiloButton { text: "Cancel"; kind: "quiet"; size: "small"; onClicked: row.editing = false }
        }

        // The Mac asks in a sheet; here the row asks, with the same words.
        Appear {
            Layout.fillWidth: true
            shown: row.asking
            visible: row.asking
            RowLayout {
                width: content.width
                spacing: 8
                MiloText { Layout.fillWidth: true; text: "Should Milo forget this?"; weight: "semibold"; wrapMode: Text.WordWrap }
                MiloButton { objectName: "keep"; text: "Keep it"; kind: "quiet"; size: "small"; onClicked: row.asking = false }
                MiloButton {
                    objectName: "confirmForget"
                    text: "Forget"
                    kind: "danger"
                    size: "small"
                    onClicked: { row.asking = false; row.forget() }
                }
            }
        }
    }
}
