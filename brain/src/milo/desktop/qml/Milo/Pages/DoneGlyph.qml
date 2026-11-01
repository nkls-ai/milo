import QtQuick
import QtQuick.Shapes
import Milo
import Milo.Controls
import "format.mjs" as Format

// The small picture of what Milo did (DoneGlyph): a calendar page with its day for an event, a checkbox row for a
// to-do, a ring that runs down for a timer, a note sheet, or a symbol on a lavender wash.
// `action` is an action_done event; `since` when its card came (a timer's ring runs from there to its end).
Item {
    id: glyph
    property var action: ({})
    property var since: new Date()
    property var now: new Date()

    readonly property var date: Format.parse(action.when)
    readonly property string symbol: ({
        reminder: "bell", alarm: "alarm", draft: "envelope", shortcut: "square.stack", music: "music.note",
        written: action.app ? "text.cursor" : "doc.on.doc", copied: "doc.on.clipboard", message: "bubble.left",
        call: "phone", sound: "speaker.wave.2", brightness: "sun.max",
        opened: String(action.detail || "").indexOf(".") >= 0 ? "globe" : "macwindow"
    })[action.kind] || "sparkles"

    implicitWidth: 36
    implicitHeight: 36
    Accessible.ignored: true

    // A tiny tear-off page: the weekday on a marigold band, the day of the month big below it.
    Rectangle {
        visible: glyph.action.kind === "event"
        anchors.fill: parent
        radius: 8
        color: Theme.card
        border.color: Theme.rule
        clip: true
        Rectangle {
            width: parent.width
            height: 12
            color: Theme.accent
            MiloText {
                anchors.centerIn: parent
                text: glyph.date ? Qt.formatDate(glyph.date, "ddd") : ""
                size: 8.5
                weight: "bold"
                rounded: true
                ink: Theme.primaryInk
            }
        }
        MiloText {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 12 + (parent.height - 12 - height) / 2
            text: glyph.date ? glyph.date.getDate() : ""
            size: 17
            weight: "bold"
            rounded: true
            tabular: true
        }
    }

    // A sheet with a marigold top and three ruled lines, a little askew.
    Rectangle {
        visible: glyph.action.kind === "note"
        anchors.centerIn: parent
        width: 32
        height: 36
        radius: 7
        rotation: -4
        color: Theme.card
        border.color: Theme.rule
        clip: true
        Rectangle { width: parent.width; height: 6; color: Theme.accent }
        Column {
            x: 6
            y: 9.5
            spacing: 3.5
            Repeater {
                model: [20, 22, 14]
                Rectangle { required property int modelData; width: modelData; height: 2; radius: 1; color: Tones.fade(Theme.ink, 0.28) }
            }
        }
    }

    // A ring that runs down from when the timer was set to when it rings, with the time left inside.
    Item {
        id: timer
        visible: glyph.action.kind === "timer"
        anchors.fill: parent
        anchors.margins: 3
        readonly property real total: Math.max(1, ((glyph.date || glyph.since) - glyph.since) / 1000)
        readonly property real remaining: Math.max(0, ((glyph.date || glyph.since) - glyph.now) / 1000)
        SmoothShape {
            anchors.fill: parent
            ShapePath {
                strokeColor: Tones.fade(Theme.primary, 0.18)
                strokeWidth: 4
                fillColor: "transparent"
                PathAngleArc { centerX: timer.width / 2; centerY: timer.height / 2; radiusX: timer.width / 2 - 2; radiusY: radiusX; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: Theme.primary
                strokeWidth: 4
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathAngleArc {
                    centerX: timer.width / 2
                    centerY: timer.height / 2
                    radiusX: timer.width / 2 - 2
                    radiusY: radiusX
                    startAngle: -90
                    sweepAngle: 360 * (glyph.date ? timer.remaining / timer.total : 1)
                }
            }
        }
        MiloText {
            anchors.centerIn: parent
            // "12m", "45s", "1h".
            text: timer.remaining >= 3600 ? Math.round(timer.remaining / 3600) + "h" : timer.remaining >= 60 ? Math.ceil(timer.remaining / 60) + "m"
                                                                                               : Math.ceil(timer.remaining) + "s"
            size: 10
            weight: "bold"
            rounded: true
            tabular: true
        }
    }

    // A checkbox with two lines beside it, like a row of a list; or a symbol, both on a lavender wash.
    Rectangle {
        visible: ["event", "note", "timer"].indexOf(glyph.action.kind) < 0
        anchors.fill: parent
        radius: 9
        color: Tones.fade(Theme.primary, 0.12)
        Row {
            visible: glyph.action.kind === "todo"
            anchors.centerIn: parent
            spacing: 4
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 11
                height: 11
                radius: 5.5
                color: "transparent"
                border.color: Theme.primary
                border.width: 1.8
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 3
                Rectangle { width: 13; height: 2.5; radius: 1.25; color: Tones.fade(Theme.primary, 0.55) }
                Rectangle { width: 9; height: 2.5; radius: 1.25; color: Tones.fade(Theme.primary, 0.3) }
            }
        }
        Icon {
            visible: glyph.action.kind !== "todo"
            anchors.centerIn: parent
            name: glyph.symbol
            size: 16
            color: Theme.primary
        }
    }
}
