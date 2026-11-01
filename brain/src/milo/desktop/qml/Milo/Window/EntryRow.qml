import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import Milo.Pages

// One line of the thread (EntryRow): the time in a gutter, then what the user said, what Milo answered or wrote,
// or a task as a card. A day's first line gets the day over it.
Column {
    id: row
    required property string entryId
    required property string kind
    required property string text
    required property string html
    required property var blocks
    required property string time
    required property bool showTime
    required property string day
    required property int gap
    required property string viaIcon
    required property string viaHelp
    required property string mood
    required property bool streaming
    required property bool written
    required property string title
    required property string status
    required property string result
    required property var steps
    required property var entry

    readonly property real gutter: 46
    topPadding: day !== "" && index > 0 ? 14 + gap : gap
    required property int index

    DayHeading {
        visible: row.day !== ""
        width: row.width
        text: row.day
        gutter: row.gutter
        bottomPadding: 10
    }

    RowLayout {
        width: row.width
        spacing: 10

        MiloText {
            Layout.preferredWidth: row.gutter
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: row.kind === "task" ? 12 : 2
            horizontalAlignment: Text.AlignRight
            text: row.showTime ? row.time : ""
            size: 10.5
            tabular: true
            tone: 0.38
        }
        Loader {
            Layout.fillWidth: true
            sourceComponent: row.kind === "user" ? user : row.kind === "task" ? task : row.written ? writtenBlock : milo
        }
    }

    Component {
        id: user
        UserLine { text: row.text; icon: row.viaIcon; help: row.viaHelp }
    }
    Component {
        id: milo
        MiloLine { text: row.text; html: row.html; blocks: row.blocks; mood: row.mood; streaming: row.streaming }
    }
    Component {
        id: writtenBlock
        WrittenBlock { text: row.text }
    }
    Component {
        id: task
        TaskCard {
            entry: row.entry
            helper: (store.helpers || []).find(h => h.id === row.entryId) || null
            undoPoint: row.status === "running" ? null : (store.undoPoints || []).find(p => p.id === row.entryId) || null
            onCommand: function(message) { shell.send(message) }
            onAction: function(name, value) { if (name === "openTask") conversations.openTask(value.id) }
        }
    }
}
