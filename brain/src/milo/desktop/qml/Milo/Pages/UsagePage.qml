import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "format.mjs" as Format

// The Usage page (UsageView.swift): how much Milo did for you, day by day, and the accounts he does it with.
//
// Inputs
//   usage: the last `usage` event, {span, today, since, daily, sources, apps, accounts}; null until it came.
//   connected: whether the brain is up ("Counting…" or "isn't running").
// Output
//   command({"type": "get_usage", span}) when the user picks another range (7, 30 or 90 days). The window sends
//   one with the current span when it opens the page; a report for another span than `span` is the window's to drop.
Item {
    id: page
    property var usage: null
    property bool connected: true
    property int span: usage ? usage.span : 30
    property string metric: "tokens"
    signal command(var message)

    readonly property var daily: usage ? usage.daily || [] : []
    function sum(key) { return daily.reduce((n, d) => n + (d[key] || 0), 0) }
    readonly property int tokens: sum("input_tokens") + sum("output_tokens")
    readonly property int cached: tokens > 0 ? Math.round(sum("cached_input_tokens") / tokens * 100) : 0
    readonly property int calls: sum("calls")
    readonly property int dictations: sum("dictations")
    readonly property int words: sum("words")
    function active(d) { return (d.calls || 0) > 0 || (d.dictations || 0) > 0 }
    readonly property int activeDays: daily.filter(active).length
    // Days in a row up to today; today may still be empty without breaking it.
    readonly property int streak: {
        let count = 0
        for (let i = daily.length - 1; i >= 0; --i) {
            if (active(daily[i])) count += 1
            else if (i !== daily.length - 1) break
        }
        return count
    }
    readonly property var sourceLabels: ({ chat: "Talking with Milo", task: "Tasks he did for you",
                                           memory: "Keeping his memory tidy", proactive: "Check-ins", heartbeat: "Check-ins" })

    MiloScrollView {
        anchors.fill: parent
        maxContentWidth: 720
        spacing: 12

        // ---- the header
        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 4
            spacing: 12
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3
                MiloText {
                    readonly property var since: page.usage ? Format.parse(page.usage.since) : null
                    text: since ? "With Milo since " + Qt.formatDate(since, "d MMMM yyyy") : "Milo on this computer"
                    size: 12; weight: "semibold"; rounded: true; ink: Theme.primary
                }
                MiloText { Layout.fillWidth: true; text: "Your usage"; size: 24; weight: "bold"; rounded: true }
            }
            MiloSegmented {
                objectName: "span"
                Layout.alignment: Qt.AlignBottom
                name: "Range"
                options: [7, 30, 90].map(n => ({ value: n, label: n + " days" }))
                current: page.span
                onPicked: value => { page.span = value; page.command({ type: "get_usage", span: value }) }
            }
        }

        EmptyState {
            visible: !page.usage
            busy: page.connected
            icon: "bolt.circle"
            title: page.connected ? "Counting…" : "Milo's brain isn't running, so there's nothing to count yet."
        }

        // ---- the headline numbers, two by two when narrow
        GridLayout {
            visible: !!page.usage
            Layout.fillWidth: true
            columns: width > 600 ? 4 : 2
            columnSpacing: 10
            rowSpacing: 10
            UsageTile {
                value: Format.compact(page.tokens); label: "Tokens"; icon: "sparkles"
                note: page.tokens > 0 ? page.cached + "% from cache" : "No model calls yet"
            }
            UsageTile {
                value: Format.compact(page.calls); label: page.calls === 1 ? "Model call" : "Model calls"
                note: "Talking, tasks, upkeep"; icon: "bubble.left.and.bubble.right"
            }
            UsageTile {
                value: Format.compact(page.dictations); label: page.dictations === 1 ? "Dictation" : "Dictations"
                note: Format.compact(page.words) + " words"; icon: "waveform"; tint: Theme.accent
            }
            UsageTile {
                value: String(page.activeDays); label: page.activeDays === 1 ? "Active day" : "Active days"
                note: page.streak > 1 ? page.streak + " days in a row" : "of the last " + page.span
                icon: "flame"; tint: Theme.accent
            }
        }

        // ---- day by day
        TitledCard {
            visible: !!page.usage
            title: "Day by day"
            icon: "chart.bar"
            MiloSegmented {
                objectName: "metric"
                name: "Show"
                options: [{ value: "tokens", label: "Tokens" }, { value: "words", label: "Words dictated" }]
                current: page.metric
                onPicked: value => page.metric = value
            }
            UsageChart {
                days: page.daily
                metric: page.metric
                tint: page.metric === "tokens" ? Theme.primary : Theme.accent
            }
        }

        // ---- where it went, side by side when there is room
        GridLayout {
            readonly property bool sources: !!page.usage && (page.usage.sources || []).length > 0
            readonly property bool apps: !!page.usage && (page.usage.apps || []).length > 0
            visible: sources || apps
            Layout.fillWidth: true
            columns: width > 560 && sources && apps ? 2 : 1
            columnSpacing: 12
            rowSpacing: 12
            TitledCard {
                visible: parent.sources
                Layout.alignment: Qt.AlignTop
                title: "Where the tokens went"
                icon: "sparkles"
                ShareBars {
                    rows: (page.usage && page.usage.sources || []).map(s => ({
                        label: page.sourceLabels[s.source] || s.source.charAt(0).toUpperCase() + s.source.slice(1),
                        value: s.tokens, shown: Format.compact(s.tokens) }))
                }
            }
            TitledCard {
                visible: parent.apps
                Layout.alignment: Qt.AlignTop
                title: "Where your words went"
                icon: "text.cursor"
                tint: Theme.accent
                ShareBars {
                    tint: Theme.accent
                    rows: (page.usage && page.usage.apps || []).map(a => ({
                        label: a.app || "Unknown app", value: a.words, shown: Format.compact(a.words) + " words" }))
                }
            }
        }

        // ---- accounts
        TitledCard {
            visible: !!page.usage
            title: "Accounts Milo uses"
            icon: "person.circle"
            RowLayout {
                visible: !page.usage || (page.usage.accounts || []).length === 0
                spacing: 8
                Spinner { size: 12 }
                MiloText { text: "Checking who Milo is signed in as…"; size: Theme.type.caption; tone: 0.55 }
            }
            Repeater {
                model: page.usage ? page.usage.accounts || [] : []
                ColumnLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: 10
                    Rule { visible: index > 0 }
                    AccountRow { account: modelData }
                }
            }
        }
    }
}
