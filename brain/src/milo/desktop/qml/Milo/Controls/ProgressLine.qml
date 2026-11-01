import QtQuick
import Milo

// How far through its plan a helper is: an empty track while it has no plan, full once it is done.
// `progress` is 0…1 or null; `status` a helper's ("queued", "working", "needs_you", "done", "failed", "stopped").
Item {
    id: line
    property var progress: null
    property string status: "working"

    readonly property bool active: status === "queued" || status === "working" || status === "needs_you"
    readonly property var fraction: status === "done" ? 1 : progress
    implicitHeight: 3
    opacity: active || progress !== null && progress !== undefined ? 1 : 0
    Accessible.role: Accessible.ProgressBar
    Accessible.name: fraction === null || fraction === undefined ? "" : Math.round(fraction * 100) + "%"

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Tones.fade(Theme.ink, 0.12)
    }
    Rectangle {
        visible: line.fraction !== null && line.fraction !== undefined
        height: parent.height
        radius: height / 2
        width: Math.max(height, parent.width * Math.min(1, line.fraction || 0))
        color: line.status === "done" ? Tones.done
             : line.status === "failed" || line.status === "stopped" ? Tones.failed
             : line.status === "needs_you" ? Theme.think : Tones.running
        Behavior on width { Spring { kind: "gentle" } }
    }
}
