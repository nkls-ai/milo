import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "routines.mjs" as Routines

// One routine (RoutineRow): what it is, its schedule and last run, Run now, and a menu to pause, resume or delete.
// `routine` is a `routines` entry; emits act(action) with "run" | "pause" | "resume" | "delete".
RowLayout {
    id: row
    property var routine: ({})
    signal act(string action)

    readonly property bool broken: !!routine.problem
    objectName: "routine-" + routine.id
    Layout.fillWidth: true
    spacing: 10

    Icon {
        Layout.alignment: Qt.AlignTop
        Layout.topMargin: 1
        Layout.preferredWidth: 18
        name: row.broken ? "exclamationmark.triangle" : row.routine.paused ? "pause.circle"
            : row.routine.schedule ? "clock" : "list.bullet"
        size: 14
        weight: "medium"
        color: row.broken ? Tones.failed : Theme.primary
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 2
        MiloText {
            Layout.fillWidth: true
            text: row.routine.name || row.routine.id || ""
            size: 12.5
            weight: "semibold"
            rounded: true
        }
        MiloText {
            Layout.fillWidth: true
            text: Routines.summary(row.routine)
            size: 11
            ink: row.broken ? Tones.failed : Theme.ink
            tone: row.broken ? 1 : 0.6
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            Tip { text: row.routine.description || ""; shown: summaryHover.hovered }
            HoverHandler { id: summaryHover }
        }
    }
    MiloButton {
        objectName: "run"
        Layout.alignment: Qt.AlignTop
        visible: !row.broken
        text: "Run now"
        kind: "outline"
        size: "small"
        tip: (row.routine.inputs || []).length ? "Do it now with the usual " + row.routine.inputs.join(", ") : "Do it now"
        Accessible.name: "Run " + row.routine.name + " now"
        onClicked: row.act("run")
    }
    PopMenu {
        objectName: "more"
        Layout.alignment: Qt.AlignTop
        visible: !row.broken
        label: "More for " + row.routine.name
        items: (row.routine.schedule ? [{ value: row.routine.paused ? "resume" : "pause",
                                          label: row.routine.paused ? "Resume the schedule" : "Pause the schedule" }] : [])
               .concat([{ value: "delete", label: "Delete", danger: true }])
        onPicked: value => row.act(value)
    }
}
