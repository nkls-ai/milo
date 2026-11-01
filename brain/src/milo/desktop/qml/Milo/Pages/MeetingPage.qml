import QtQuick
import QtQuick.Layouts
import Milo
import Milo.Controls
import "meeting.mjs" as Meeting
import "wire.mjs" as Wire

// A meeting in the Milo window (MeetingPage.swift). While it goes on: who speaks, the transcript as it comes in, Pause
// and Stop, a line to paste into the call's chat, and a field to ask about it. Afterwards: the notes, the to-dos with
// "Add to Reminders", and the transcript. See docs/design/meetings.md.
//
// Inputs
//   meetingId:    the meeting's folder name (a meeting conversation's source after "meeting:")
//   conversation: the meeting's conversation id, where questions about it go
//   status:       the latest `meeting_status` event ({id, phase, title, app, elapsed, speakers, step, consent, …})
//   lines:        this meeting's `meeting_lines` so far, [{at, end, who, me, text}]
//   notes:        its `meeting_notes` event, or null while they haven't come
//   entries:      the meeting conversation's entries ([{id, kind, text, …}]), for questions and answers
//   copied:       the consent line was just copied; copiedNotes: the notes were just copied
//   tab:          "notes" | "todos" | "transcript", the tab it opens on
// Output
//   command: {"type": "open_meeting", id} on opening, "meeting_pause" {on}, "meeting_toggle" {on: false} (Stop),
//            "meeting_todo" {id, index} (-1 for all of mine), "meeting_mail" {id}, "text" {text, speak, conversation}
//   action:  "copyConsent" (the line), "copyNotes" (notes.markdown), "reveal" (a path to show in its folder)
Item {
    id: page
    property string meetingId: ""
    property string conversation: ""
    property var status: ({})
    property var lines: []
    property var notes: null
    property var entries: []
    property bool copied: false
    property bool copiedNotes: false
    property string tab: "notes"
    signal command(var message)
    signal action(string name, var value)

    readonly property bool current: Meeting.current(status, meetingId)
    readonly property var questions: Meeting.questions(entries)
    readonly property string consentLine: status.consent || Meeting.consent
    // The notes didn't come within three seconds: the page shows the meeting's conversation as it is.
    property bool missing: false

    // Seconds into the meeting, counted on between meeting_status events while it records.
    property real elapsed: status.elapsed || 0
    onStatusChanged: elapsed = status.elapsed || 0
    Timer {
        interval: 1000
        repeat: true
        running: page.current && page.status.phase === "recording"
        onTriggered: page.elapsed += 1
    }
    Timer {
        interval: 3000
        running: true
        onTriggered: page.missing = !page.notes && !page.current
    }
    // Asked for once the page is up, after whoever shows it has connected `command`.
    Component.onCompleted: if (meetingId) Qt.callLater(() => command({ type: "open_meeting", id: meetingId }))

    function ask(text) { command(Wire.text(text, conversation)) }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---- going on
        LiveMeetingHeader {
            visible: page.current
            status: page.status
            elapsed: page.elapsed
            onPause: on => page.command({ type: "meeting_pause", on: on })
            onStop: page.command({ type: "meeting_toggle", on: false })
        }
        ConsentRow {
            visible: page.current && Meeting.live(page.status)
            line: page.consentLine
            copied: page.copied
            onCopy: page.action("copyConsent", page.consentLine)
        }
        MeetingTranscript {
            visible: page.current
            lines: page.lines
            phase: page.status.phase || ""
            step: page.status.step || ""
            live: true
        }

        // ---- done
        NotesHeader {
            visible: !page.current && !!page.notes
            notes: page.notes || {}
            copied: page.copiedNotes
            onCopy: page.action("copyNotes", page.notes.markdown)
            onReveal: path => page.action("reveal", path)
        }
        MeetingTabs {
            visible: !page.current && !!page.notes
            tab: page.tab
            todos: page.notes ? (page.notes.todos || []).length : 0
            onPicked: tab => page.tab = tab
        }
        MiloScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.current && !!page.notes && page.tab === "notes"
            leftPadding: 24
            rightPadding: 24
            topPadding: 18
            bottomPadding: 18
            maxContentWidth: 680
            spacing: 18

            NotesText {
                markdown: page.notes ? Meeting.notesBody(page.notes.markdown) : ""
                // The transcript link opens its tab. Nothing else opens: the notes are written from other people's words.
                onLink: url => { if (Meeting.ownLink(url)) page.tab = "transcript" }
            }
            MiloButton {
                objectName: "mail"
                visible: !!page.notes && !!page.notes.mail && !!page.notes.followup
                enabled: !!page.notes && !page.notes.mail_drafted
                text: page.notes && page.notes.mail_drafted ? "The draft is in Mail" : "Put the mail in Mail as a draft"
                kind: page.notes && page.notes.mail_drafted ? "quiet" : "primary"
                onClicked: page.command({ type: "meeting_mail", id: page.meetingId })
            }
        }
        MeetingTodos {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.current && !!page.notes && page.tab === "todos"
            notes: page.notes || {}
            onAdd: index => page.command({ type: "meeting_todo", id: page.meetingId, index: index })
        }
        MeetingTranscript {
            visible: !page.current && !!page.notes && page.tab === "transcript"
            lines: page.lines
            phase: "done"
            live: false
        }

        // ---- the notes didn't come: the conversation as it is
        MiloScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.current && !page.notes && page.missing
            leftPadding: 18
            topPadding: 14
            spacing: 10
            Repeater {
                model: page.entries
                MiloText {
                    required property var modelData
                    Layout.fillWidth: true
                    text: modelData.text
                    wrapMode: Text.WordWrap
                    ink: modelData.kind === "user" ? Theme.ink : Theme.primary
                    tone: modelData.kind === "user" ? 0.7 : 1
                }
            }
        }

        // ---- opening
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !page.current && !page.notes && !page.missing
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 10
                ThinkingDots { Layout.alignment: Qt.AlignHCenter }
                MiloText { text: "Opening the notes…"; weight: "medium"; rounded: true; tone: 0.6 }
            }
        }

        AskAboutMeeting {
            visible: page.current || !!page.notes || page.missing
            entries: page.questions
            suggestions: page.current ? ["What did I miss?", "Sum up the last ten minutes"]
                                      : page.notes ? ["What do I need to do?", "Write a short recap"] : []
            onAsk: text => page.ask(text)
        }
    }
}
