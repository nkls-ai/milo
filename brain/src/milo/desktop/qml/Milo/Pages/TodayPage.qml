import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import Milo
import Milo.Controls
import "format.mjs" as Format
import "tasks.mjs" as Tasks
import "wire.mjs" as Wire

// Home (TodayView.swift): what Milo is doing now, what waits for you, today's reminders, what got done, this week's
// meetings, and where you left off. Its cards float in one after another.
//
// Inputs
//   helpers: the `helpers` event's list, [{id, title, status, step, progress}].
//   reminders: the `reminders` event's list, [{due, text}].
//   conversations: the `conversations` event's list, [{id, kind, started, last, title, preview, tasks, via, source}].
//   current: the `conversations` event's `current` id: picking that one up goes back to the live conversation.
//   question: the pending `confirm` event, {id, question, always, money, choices?}, or null.
//   drafts: the `routines` event's drafts, [{id, name, recipe, schedule}].
//   routines: the `routines` event's routines.
//   undoPoints: the `undo_points` event's points, [{id, title, state}].
//   meeting: the last `meeting_status` event, or {}.
//   talkKey: the talk key in words, "Right Alt".
//   now: the clock; entrance: false shows the cards at once (renders).
// Outputs
//   command: confirm_answer, stop_helper, undo_task, routine_draft_answer, routine.
//   action("openTask", {id, conversation}), action("openConversation", id), action("live", ""),
//   action("changeDraft", draft).
Item {
    id: page
    property var helpers: []
    property var reminders: []
    property var conversations: []
    property string current: ""
    property var question: null
    property var drafts: []
    property var routines: []
    property var undoPoints: []
    property var meeting: ({})
    property string talkKey: "Right Alt"
    property var now: new Date()
    // `now` as a Date; a sample may give it as "2026-10-30T16:20".
    readonly property var clock: typeof now === "string" ? Format.parse(now) : now
    property bool entrance: true
    signal command(var message)
    signal action(string name, var value)

    // ---- what goes in

    readonly property var working: (helpers || []).filter(h => Tasks.active(h.status))
    readonly property bool waiting: !!question || (drafts || []).length > 0
    readonly property var doneToday: {
        const items = []
        for (const c of conversations || [])
            for (const t of c.tasks || []) {
                const at = Format.parse(t.at)
                if (t.status !== "running" && at && Format.sameDay(at, clock)) items.push({ task: t, conversation: c, at: at })
            }
        return items.sort((a, b) => b.at - a.at).slice(0, 5)
    }
    // Meetings of the last seven days, newest first, at most four.
    readonly property var meetings: {
        const since = new Date(clock.getTime() - 7 * 86400000)
        return (conversations || []).filter(c => c.kind === "meeting" && Format.parse(c.started) >= since)
            .sort((a, b) => Format.parse(b.started) - Format.parse(a.started)).slice(0, 4)
    }
    readonly property var lastConversation: (conversations || []).find(c => c.kind === "chat") || null
    readonly property bool quiet: working.length === 0 && !waiting && (reminders || []).length === 0
                                  && doneToday.length === 0 && !lastConversation && meetings.length === 0
    // The cards showing, in order, for the entrance's stagger.
    readonly property var order: ["waiting", "working", "reminders", "done", "meetings", "pickUp", "routines"].filter(name => ({
        waiting: waiting, working: working.length > 0, reminders: (reminders || []).length > 0,
        done: doneToday.length > 0, meetings: meetings.length > 0, pickUp: !!lastConversation,
        routines: (routines || []).length > 0 })[name])

    readonly property string greeting: {
        const hour = clock.getHours()
        return hour >= 5 && hour < 12 ? "Good morning." : hour >= 12 && hour < 18 ? "Good afternoon."
             : hour >= 18 && hour < 23 ? "Good evening." : "Still up?"
    }
    // One quiet line under the greeting: "Waiting for your answer · 1 thing in progress · 2 done today".
    readonly property string summary: {
        const parts = []
        if (waiting) parts.push("Waiting for your answer")
        if (working.length) parts.push(working.length === 1 ? "1 thing in progress" : working.length + " things in progress")
        if (doneToday.length) parts.push(doneToday.length + " done today")
        return parts.length ? parts.join(" · ") : "Here's your day with Milo."
    }

    function undoPoint(id) { return (undoPoints || []).find(p => p.id === id) || null }
    function cardIndex(name) { return order.indexOf(name) + 1 }

    MiloScrollView {
        anchors.fill: parent
        spacing: 12

        // ---- the header
        Entrance {
            Layout.bottomMargin: 4
            animated: page.entrance
            RowLayout {
                Layout.fillWidth: true
                spacing: 14
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    MiloText {
                        text: Format.longDay(page.clock)
                        size: Theme.type.caption
                        weight: "semibold"
                        rounded: true
                        ink: Theme.primary
                    }
                    MiloText {
                        text: page.greeting
                        size: 24
                        weight: "bold"
                        rounded: true
                        Accessible.role: Accessible.Heading
                    }
                    MiloText {
                        Layout.fillWidth: true
                        text: page.summary
                        size: 12.5
                        tone: 0.58
                        wrapMode: Text.WordWrap
                    }
                }
                Item {
                    implicitWidth: 58
                    implicitHeight: 58
                    // A soft glow behind him, fading out from his middle.
                    SmoothShape {
                        anchors.centerIn: parent
                        width: 96
                        height: 96
                        ShapePath {
                            strokeColor: "transparent"
                            fillGradient: RadialGradient {
                                centerX: 48; centerY: 48; centerRadius: 46
                                focalX: 48; focalY: 48; focalRadius: 4
                                GradientStop { position: 0; color: Tones.fade(Theme.glow, 0.5) }
                                GradientStop { position: 1; color: Tones.fade(Theme.glow, 0) }
                            }
                            PathAngleArc { centerX: 48; centerY: 48; radiusX: 48; radiusY: 48; sweepAngle: 360 }
                        }
                    }
                    WrenSlot {
                        anchors.fill: parent
                        size: 58
                        mood: page.question ? "thinking" : page.working.length === 0 ? "happy" : "excited"
                    }
                }
            }
        }

        // ---- nothing going on
        Entrance {
            visible: page.quiet
            index: 1
            animated: page.entrance
            EmptyState {
                framed: true
                icon: "leaf"
                title: "Nothing on your plate."
                detail: "Hold " + page.talkKey + " and talk to Milo, or type below. What you ask for, and what he does, shows up here."
            }
        }

        // ---- waiting for you
        Entrance {
            visible: page.waiting
            index: page.cardIndex("waiting")
            animated: page.entrance
            TitledCard {
                title: "Waiting for you"
                icon: "hand.raised"
                tint: Theme.accent
                RowLayout {
                    Layout.fillWidth: true
                    visible: !!page.question
                    spacing: 12
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        MiloText {
                            Layout.fillWidth: true
                            text: page.question ? page.question.question : ""
                            size: 13.5
                            weight: "medium"
                            rounded: true
                            wrapMode: Text.WordWrap
                        }
                        MiloText {
                            Layout.fillWidth: true
                            text: page.question && page.question.money
                                  ? "This involves money. Only a click on Yes counts for this, not a spoken yes."
                                  : "Or hold " + page.talkKey + " and say yes or no."
                            size: 11
                            ink: page.question && page.question.money ? Theme.accent : Theme.ink
                            tone: page.question && page.question.money ? 1 : 0.5
                            wrapMode: Text.WordWrap
                        }
                    }
                    AnswerButtons {
                        objectName: "answers"
                        Layout.preferredWidth: implicitWidth
                        always: !!page.question && !!page.question.always
                        choices: page.question && page.question.choices ? page.question.choices : []
                        onAnswered: choice => page.command(Wire.confirmAnswer(page.question, choice))
                    }
                }
                Repeater {
                    model: page.drafts
                    Loader {
                        id: draft
                        required property var modelData
                        Layout.fillWidth: true
                        objectName: "draft-" + modelData.id
                        source: "DraftCard.qml"
                        onLoaded: {
                            item.draft = Qt.binding(() => draft.modelData)
                            item.talkKey = Qt.binding(() => page.talkKey)
                            item.command.connect(page.command)
                            item.action.connect(page.action)
                        }
                    }
                }
            }
        }

        // ---- at work
        Entrance {
            visible: page.working.length > 0
            index: page.cardIndex("working")
            animated: page.entrance
            TitledCard {
                title: page.working.length === 1 ? "Milo is working on" : "Milo is working on " + page.working.length + " things"
                icon: "sparkles"
                tint: Tones.running
                Repeater {
                    model: page.working
                    HelperRow {
                        required property var modelData
                        helper: modelData
                        onOpen: id => page.action("openTask", { id: id, conversation: "" })
                        onStop: id => page.command(Wire.stopHelper(id))
                    }
                }
                MiloButton {
                    objectName: "stopAll"
                    Layout.alignment: Qt.AlignRight
                    visible: page.working.length > 1
                    text: "Stop all"
                    kind: "plain"
                    size: "small"
                    tint: Tones.failed
                    onClicked: page.working.forEach(h => page.command(Wire.stopHelper(h.id)))
                }
            }
        }

        // ---- reminders
        Entrance {
            visible: (page.reminders || []).length > 0
            index: page.cardIndex("reminders")
            animated: page.entrance
            TitledCard {
                title: "Reminders"
                icon: "bell"
                tint: Theme.primary
                Repeater {
                    model: page.reminders
                    RowLayout {
                        required property var modelData
                        readonly property var due: Format.parse(modelData.due)
                        spacing: 10
                        MiloText {
                            Layout.preferredWidth: 74
                            Layout.alignment: Qt.AlignTop
                            text: due ? Format.due(due, page.clock) : ""
                            size: 11.5
                            weight: "semibold"
                            rounded: true
                            tabular: true
                            ink: due && due < page.clock ? Theme.accent : Theme.primary
                        }
                        MiloText { Layout.fillWidth: true; text: modelData.text; wrapMode: Text.WordWrap }
                    }
                }
            }
        }

        // ---- done today
        Entrance {
            visible: page.doneToday.length > 0
            index: page.cardIndex("done")
            animated: page.entrance
            TitledCard {
                title: "Done today"
                icon: "checkmark.seal"
                tint: Tones.done
                Repeater {
                    model: page.doneToday
                    RowLayout {
                        required property var modelData
                        objectName: "done-" + modelData.task.id
                        spacing: 8
                        RowButton {
                            objectName: "open"
                            label: modelData.task.title + ", in " + modelData.conversation.title
                            onClicked: page.action("openTask", { id: modelData.task.id, conversation: modelData.conversation.id })
                            contentItem: RowLayout {
                                spacing: 10
                                StatusSeal { status: modelData.task.status; size: 20 }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    MiloText { Layout.fillWidth: true; text: modelData.task.title; weight: "medium"; rounded: true }
                                    MiloText {
                                        Layout.fillWidth: true
                                        text: "in “" + modelData.conversation.title + "”"
                                        size: 11
                                        tone: 0.5
                                    }
                                }
                                MiloText { text: Format.time(modelData.at); size: 10.5; tone: 0.42; tabular: true }
                                Icon { name: "chevron.right"; size: 9; weight: "bold"; color: Tones.fade(Theme.ink, 0.3) }
                            }
                        }
                        // Beside the row, not in it: a button inside its button would open the task instead.
                        UndoButton {
                            objectName: "undo"
                            visible: !!page.undoPoint(modelData.task.id)
                            point: page.undoPoint(modelData.task.id) || ({})
                            onUndo: id => page.command(Wire.undoTask(id))
                        }
                    }
                }
            }
        }

        // ---- this week's meetings, the one going on first
        Entrance {
            visible: page.meetings.length > 0
            index: page.cardIndex("meetings")
            animated: page.entrance
            TitledCard {
                title: "Meetings"
                icon: "person.2"
                tint: Theme.accent
                Repeater {
                    model: page.meetings
                    RowButton {
                        required property var modelData
                        readonly property string phase: page.meeting && page.meeting.conversation === modelData.id ? page.meeting.phase || "" : ""
                        readonly property bool live: phase !== "" && phase !== "done"
                        objectName: "meeting-" + modelData.id
                        label: modelData.title
                        Accessible.description: live ? "Opens the live transcript" : "Opens the notes"
                        onClicked: page.action("openConversation", modelData.id)
                        contentItem: RowLayout {
                            spacing: 10
                            Item {
                                implicitWidth: 20
                                implicitHeight: 20
                                LiveLight { anchors.centerIn: parent; visible: live; paused: phase === "paused" }
                                Icon { anchors.centerIn: parent; visible: !live; name: "note.text"; size: 12; color: Theme.accent }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                MiloText { Layout.fillWidth: true; text: modelData.title; weight: "medium"; rounded: true }
                                MiloText {
                                    Layout.fillWidth: true
                                    text: live ? (phase === "writing" ? "Writing the notes…" : "Taking notes now")
                                               : Tasks.meetingSummary(modelData.preview)
                                    size: 11
                                    tone: live ? 0.7 : 0.5
                                }
                            }
                            MiloText { text: Format.rowTime(Format.parse(modelData.started), page.clock); size: 10.5; tone: 0.42; tabular: true }
                            Icon { name: "chevron.right"; size: 9; weight: "bold"; color: Tones.fade(Theme.ink, 0.3) }
                        }
                    }
                }
            }
        }

        // ---- pick up where you left off
        Entrance {
            visible: !!page.lastConversation
            index: page.cardIndex("pickUp")
            animated: page.entrance
            RowButton {
                objectName: "pickUp"
                readonly property var c: page.lastConversation || ({})
                card: true
                radius: 16
                horizontalPadding: 14
                verticalPadding: 14
                label: "Pick up where you left off: " + (c.title || "")
                onClicked: c.id === page.current ? page.action("live", "") : page.action("openConversation", c.id)
                contentItem: RowLayout {
                    spacing: 12
                    Rectangle {
                        implicitWidth: 30
                        implicitHeight: 30
                        radius: 15
                        color: Tones.fade(Theme.primary, 0.12)
                        Icon { anchors.centerIn: parent; name: "arrow.uturn.backward"; size: 13; weight: "bold"; color: Theme.primary }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        MiloText { text: "Pick up where you left off"; size: 11; weight: "semibold"; rounded: true; tone: 0.5 }
                        RowLayout {
                            spacing: 5
                            // KindMark: a phone for a conversation from the phone.
                            Icon {
                                visible: !!page.lastConversation && (page.lastConversation.via || []).indexOf("message") >= 0
                                name: "iphone"
                                size: 10
                                color: Tones.fade(Theme.ink, 0.55)
                            }
                            MiloText {
                                Layout.fillWidth: true
                                text: page.lastConversation ? page.lastConversation.title : ""
                                size: 13.5
                                weight: "semibold"
                                rounded: true
                            }
                        }
                        MiloText {
                            Layout.fillWidth: true
                            visible: !!page.lastConversation && !!page.lastConversation.preview
                            text: page.lastConversation ? page.lastConversation.preview || "" : ""
                            size: 11.5
                            tone: 0.55
                        }
                    }
                    MiloText {
                        text: page.lastConversation ? Format.rowTime(Format.parse(page.lastConversation.last), page.clock) : ""
                        size: 10.5
                        tone: 0.42
                        tabular: true
                    }
                }
            }
        }

        // ---- routines
        Entrance {
            visible: (page.routines || []).length > 0
            index: page.cardIndex("routines")
            animated: page.entrance
            Loader {
                id: routinesPanel
                Layout.fillWidth: true
                active: (page.routines || []).length > 0
                source: "RoutinesPanel.qml"
                onLoaded: {
                    item.routines = Qt.binding(() => page.routines)
                    item.command.connect(page.command)
                }
            }
        }
    }
}
