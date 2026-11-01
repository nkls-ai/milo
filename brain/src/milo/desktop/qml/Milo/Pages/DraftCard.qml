import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "routines.mjs" as Routines

// A recipe Milo wrote down, waiting for the user's look (DraftCard): its steps and inputs, Save, Change it, and a way
// to throw it away. `draft` is a `routines` event's draft {id, name, recipe, schedule}; `talkKey` the talk key's name.
// Emits save(), change() and drop().
Rectangle {
    id: card
    property var draft: ({})
    property string talkKey: "Right Alt"
    signal save()
    signal change()
    signal drop()

    // Shows the file exactly as Save writes it, front matter and all.
    property bool whole: false
    readonly property var inputs: Routines.inputs(draft.recipe)
    readonly property var apps: Routines.apps(draft.recipe)

    objectName: "draft-" + draft.id
    Layout.fillWidth: true
    implicitHeight: column.implicitHeight + 24
    color: Tones.fade(Theme.ink, 0.05)
    Accessible.role: Accessible.Grouping
    Accessible.name: "Milo wrote down " + draft.name

    Rule { anchors.top: parent.top; width: parent.width }

    ColumnLayout {
        id: column
        x: 16
        y: 12
        width: parent.width - 32
        spacing: 8

        RowLayout {
            spacing: 8
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                MiloText { Layout.fillWidth: true; text: "New routine: " + card.draft.name; size: 13.5; weight: "semibold"; rounded: true }
                MiloText {
                    text: card.draft.schedule ? "Runs " + card.draft.schedule + "." : "Runs when you ask for it."
                    size: 11
                    tone: 0.6
                }
            }
            IconButton {
                objectName: "drop"
                Layout.alignment: Qt.AlignTop
                iconName: "xmark"
                label: "Throw this recipe away"
                Accessible.name: "Throw away"
                size: 20
                wash: false
                tone: 0.6
                onClicked: card.drop()
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: Math.min(190, recipe.implicitHeight + 20)
            radius: 9
            color: Theme.card
            Flickable {
                id: scroller
                anchors.fill: parent
                anchors.margins: 10
                contentHeight: recipe.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ColumnLayout {
                    id: recipe
                    width: scroller.width
                    spacing: 6
                    TextEdit {
                        visible: card.whole
                        Layout.fillWidth: true
                        text: card.draft.recipe || ""
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        color: Theme.ink
                        selectionColor: Tones.fade(Theme.primary, 0.35)
                        font.family: "Consolas, Cascadia Mono, DejaVu Sans Mono, monospace"
                        font.pixelSize: 11
                    }
                    MiloText {
                        visible: !card.whole && card.inputs.length > 0
                        Layout.fillWidth: true
                        text: "Each time: " + card.inputs.join("; ")
                        size: 11.5
                        weight: "medium"
                        ink: Theme.primary
                        wrapMode: Text.WordWrap
                    }
                    MiloText {
                        visible: !card.whole && card.apps.length > 0
                        Layout.fillWidth: true
                        text: "Uses the screen with " + card.apps.join(", ")
                        size: 11.5
                        weight: "medium"
                        ink: Theme.primary
                        wrapMode: Text.WordWrap
                    }
                    Repeater {
                        model: card.whole ? [] : Routines.lines(Routines.steps(card.draft.recipe))
                        MiloText {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.topMargin: modelData.heading ? 4 : 0
                            text: modelData.text
                            size: modelData.heading ? 12.5 : 12
                            weight: modelData.heading ? "semibold" : "regular"
                            rounded: modelData.heading
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }
        RowLayout {
            spacing: 8
            MiloButton {
                objectName: "whole"
                text: card.whole ? "Show the steps" : "Show the whole file"
                kind: "plain"
                size: "small"
                tint: Tones.fade(Theme.ink, 0.6)
                tip: "The file exactly as Save keeps it"
                onClicked: card.whole = !card.whole
            }
            Item { Layout.fillWidth: true }
            MiloButton {
                objectName: "change"
                text: "Change it"
                kind: "quiet"
                size: "small"
                tip: "Type what to change, or hold " + card.talkKey + " and say it"
                onClicked: card.change()
            }
            MiloButton {
                objectName: "save"
                text: "Save"
                size: "small"
                onClicked: card.save()
            }
        }
    }
}
