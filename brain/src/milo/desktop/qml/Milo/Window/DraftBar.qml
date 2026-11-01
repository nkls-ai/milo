import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls

// A recipe Milo wrote down and waits on the user's look for: Save it, change it in words, or throw it away.
Rectangle {
    id: bar
    property var draft: ({})
    implicitHeight: row.implicitHeight + 22
    color: Tones.fade(Theme.primary, 0.05)

    Rule { anchors { left: parent.left; right: parent.right; top: parent.top } }

    RowLayout {
        id: row
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 16; rightMargin: 12 }
        spacing: 10

        Icon { name: "arrow.loop"; size: 14; color: Theme.primary }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            MiloText { Layout.fillWidth: true; text: "New routine: " + (bar.draft.name || ""); size: 13; weight: "semibold"; rounded: true }
            MiloText {
                Layout.fillWidth: true
                text: bar.draft.schedule ? "Runs " + bar.draft.schedule + "." : "Runs when you ask for it."
                size: 11.5
                tone: 0.55
            }
        }
        MiloButton {
            kind: "primary"
            size: "small"
            text: "Save"
            onClicked: shell.send({ type: "routine_draft_answer", id: bar.draft.id, save: true })
        }
        MiloButton { kind: "quiet"; size: "small"; text: "Change it"; onClicked: shell.changeDraft(bar.draft.name || "") }
        IconButton {
            iconName: "xmark"
            label: "Throw this routine away"
            size: 22
            onClicked: shell.send({ type: "routine_draft_answer", id: bar.draft.id, save: false })
        }
    }
}
