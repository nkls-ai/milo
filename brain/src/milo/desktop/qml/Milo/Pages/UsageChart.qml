import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "format.mjs" as Format

// Bars for each day of the range, one series (DailyChart in UsageView.swift). Hovering a day shows its numbers.
// `days` are the usage event's `daily`; `metric` "tokens" or "words".
Item {
    id: chart
    property var days: []
    property string metric: "tokens"
    property color tint: Theme.primary
    property int hovered: -1

    function value(d) { return metric === "tokens" ? (d.input_tokens || 0) + (d.output_tokens || 0) : (d.words || 0) }
    readonly property var values: days.map(d => value(d))
    readonly property real ceiling: {
        const most = Math.max(1, ...values)
        // A round top, so the three grid lines land on plain numbers.
        const step = 3 * Math.pow(10, Math.floor(Math.log10(most / 3)))
        return Math.ceil(most / step) * step
    }
    readonly property bool empty: values.every(v => v === 0)
    readonly property real axis: 40
    readonly property real base: 18
    readonly property real plot: height - base - 4

    implicitHeight: 170
    Layout.fillWidth: true
    Accessible.role: Accessible.Chart
    Accessible.name: (metric === "tokens" ? "Tokens" : "Words dictated") + " per day"

    // The grid: three lines with their numbers on the left.
    Repeater {
        model: 3
        Item {
            required property int index
            readonly property real share: (index + 1) / 3
            width: chart.width
            y: 4 + chart.plot * (1 - share)
            Rectangle { x: chart.axis; width: parent.width - chart.axis; height: 1; color: Theme.rule }
            MiloText {
                width: chart.axis - 6
                y: -height / 2
                horizontalAlignment: Text.AlignRight
                text: Format.compact(Math.round(chart.ceiling * parent.share))
                size: 10
                tone: 0.45
                tabular: true
            }
        }
    }
    Rectangle { x: chart.axis; y: 4 + chart.plot; width: chart.width - chart.axis; height: 1; color: Theme.rule }

    Row {
        id: bars
        x: chart.axis + 4
        y: 4
        width: chart.width - chart.axis - 8
        height: chart.plot
        readonly property real slot: chart.days.length ? width / chart.days.length : width
        Repeater {
            model: chart.days
            Item {
                id: day
                required property var modelData
                required property int index
                width: bars.slot
                height: bars.height
                readonly property real v: chart.value(modelData)
                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: Math.max(2, Math.min(22, bars.slot * 0.62))
                    height: day.v > 0 ? Math.max(2, bars.height * day.v / chart.ceiling) : 0
                    // Rounded on top only: the bottom corners hide under the base line.
                    radius: Math.min(4, width / 2)
                    color: Tones.fade(chart.tint, chart.hovered < 0 || chart.hovered === day.index ? 1 : 0.45)
                    Behavior on height { Spring { kind: "gentle" } }
                }
                HoverHandler { onHoveredChanged: chart.hovered = hovered ? day.index : (chart.hovered === day.index ? -1 : chart.hovered) }
                // Day labels, about six across.
                MiloText {
                    visible: day.index % Math.max(1, Math.ceil(chart.days.length / 6)) === 0
                    y: bars.height + 4
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: Qt.formatDate(Format.parse(day.modelData.day), "d MMM")
                    size: 10
                    tone: 0.45
                }
            }
        }
    }

    // The hovered day's rule and numbers.
    Rectangle {
        visible: chart.hovered >= 0
        x: bars.x + bars.slot * (chart.hovered + 0.5)
        y: 4
        width: 1
        height: chart.plot
        color: Tones.fade(Theme.ink, 0.12)
        z: -1
    }
    Surface {
        id: tip
        visible: chart.hovered >= 0
        readonly property var d: chart.hovered >= 0 ? chart.days[chart.hovered] : null
        width: tipText.implicitWidth + 18
        height: tipText.implicitHeight + 12
        x: Math.max(0, Math.min(chart.width - width, bars.x + bars.slot * (chart.hovered + 0.5) - width / 2))
        y: 0
        radius: 9
        lift: 0.12
        liftRadius: 6
        liftY: 2
        Column {
            id: tipText
            x: 9
            y: 6
            spacing: 2
            MiloText {
                text: tip.d ? Qt.formatDate(Format.parse(tip.d.day), "ddd d MMM") : ""
                size: 10.5; weight: "semibold"; rounded: true; tone: 0.6
            }
            MiloText {
                text: !tip.d ? "" : chart.metric === "tokens" ? chart.value(tip.d).toLocaleString(Qt.locale(), "f", 0) + " tokens"
                                                              : chart.value(tip.d).toLocaleString(Qt.locale(), "f", 0) + " words"
                size: 12; weight: "bold"; rounded: true
            }
            MiloText {
                text: !tip.d ? "" : chart.metric === "tokens" ? tip.d.calls + (tip.d.calls === 1 ? " call" : " calls")
                                                              : tip.d.dictations + (tip.d.dictations === 1 ? " dictation" : " dictations")
                size: 10.5; tone: 0.6
            }
        }
    }

    MiloText {
        anchors.centerIn: parent
        visible: chart.empty
        text: chart.metric === "tokens" ? "No model calls in this range." : "Nothing dictated in this range."
        size: Theme.type.caption
        tone: 0.5
    }
}
