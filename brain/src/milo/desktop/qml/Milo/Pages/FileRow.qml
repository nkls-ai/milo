import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "tasks.mjs" as Tasks

// A file a task named (FileRow in TaskPage.swift): an icon, its name, its folder, and Show in folder.
RowLayout {
    id: row
    property string path
    signal reveal()

    Layout.fillWidth: true
    Layout.leftMargin: 10
    Layout.rightMargin: 10
    Layout.topMargin: 8
    Layout.bottomMargin: 8
    spacing: 10
    objectName: "file-" + Tasks.fileName(path)

    HoverHandler { id: hover }

    Rectangle {
        implicitWidth: 22
        implicitHeight: 22
        radius: 5
        color: Tones.fade(Theme.primary, 0.12)
        Icon { anchors.centerIn: parent; name: "doc.text"; size: 13; color: Theme.primary; weight: "medium" }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 1
        MiloText { Layout.fillWidth: true; text: Tasks.fileName(row.path); size: 12.5; weight: "medium" }
        MiloText {
            Layout.fillWidth: true
            text: Tasks.folder(row.path)
            size: 11
            tone: 0.5
            elide: Text.ElideMiddle
        }
    }
    MiloButton {
        objectName: "reveal"
        text: "Show in folder"
        kind: "secondary"
        size: "small"
        opacity: hover.hovered || activeFocus ? 1 : 0.75
        onClicked: row.reveal()
    }
}
