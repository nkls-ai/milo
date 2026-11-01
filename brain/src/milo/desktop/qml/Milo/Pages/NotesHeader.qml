import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "meeting.mjs" as Meeting

// The top of finished notes (NotesHeader): the title, when and how long, who was there, Copy and Show in folder.
// The buttons keep their words where there is room and only their icons where there isn't.
Item {
    id: header
    property var notes: ({})
    property bool copied: false
    signal copy()
    signal reveal(string path)

    readonly property bool narrow: width < 520
    Layout.fillWidth: true
    implicitHeight: row.implicitHeight + 28

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 20
        anchors.rightMargin: 20
        spacing: 12

        Rectangle {
            implicitWidth: 34
            implicitHeight: 34
            radius: 9
            color: Tones.fade(Theme.accent, 0.14)
            Icon { anchors.centerIn: parent; name: "person.2"; size: 15; color: Theme.accent }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 190
            spacing: 3
            MiloText {
                Layout.fillWidth: true
                text: header.notes.title || "Meeting"
                size: Theme.type.headline
                weight: "bold"
                rounded: true
            }
            MiloText {
                Layout.fillWidth: true
                text: Meeting.notesLine(header.notes)
                size: Theme.type.caption
                tone: 0.58
            }
        }
        MiloButton {
            objectName: "copyNotes"
            text: header.copied ? "Copied" : "Copy notes"
            iconName: header.copied ? "check" : "doc.on.doc"
            iconOnly: header.narrow
            kind: "quiet"
            tip: "Copy the notes, to paste them anywhere"
            onClicked: header.copy()
        }
        MiloButton {
            objectName: "reveal"
            visible: !!header.notes.folder
            text: "Show in folder"
            iconName: "folder"
            iconOnly: header.narrow
            kind: "quiet"
            tip: "Show notes.md in its folder"
            onClicked: header.reveal(header.notes.folder + "/notes.md")
        }
    }
}
