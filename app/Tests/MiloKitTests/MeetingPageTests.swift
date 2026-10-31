import Foundation
import Testing
@testable import MiloKit

/// What the app shows of meeting notes: the capsule's status, the live page's lines and how it follows them, the
/// notes page, and the bubbles that go with each step. See docs/design/meetings.md.
@Suite struct MeetingPageTests {
    private func status(_ phase: MeetingStatus.Phase, elapsed: Double = 60, error: String = "",
                        fix: MeetingStatus.Fix = .none, step: String = "") -> MeetingStatus {
        MeetingStatus(id: "m1", phase: phase, title: "Weekly sync", app: "Zoom", elapsed: elapsed, conversation: "c1",
                      speakers: ["You", "Anna"], step: step, error: error, fix: fix, consent: "Milo is taking notes.")
    }

    @Test func linesStreamInOrderAndANamedSpeakerReplacesItsLine() {
        let meeting = MeetingModel()
        meeting.apply(.meetingLines(id: "m1", lines: [MeetingLine(at: 30, who: "Speaker 2", text: "Second")], reset: false))
        meeting.apply(.meetingLines(id: "m1", lines: [MeetingLine(at: 4, who: "You", me: true, text: "First")], reset: false))
        meeting.apply(.meetingLines(id: "m1", lines: [MeetingLine(at: 30, who: "Anna", text: "Second")], reset: false))
        #expect(meeting.lines["m1"]?.map(\.who) == ["You", "Anna"])
        meeting.apply(.meetingLines(id: "m1", lines: [MeetingLine(at: 50, who: "Anna", text: "Only")], reset: true))
        #expect(meeting.lines["m1"]?.map(\.text) == ["Only"])
    }

    @Test func theClockCountsWhileItRecordsAndStandsStillOnceStopped() {
        var now = 100.0
        let meeting = MeetingModel(clock: { now })
        meeting.apply(.meetingStatus(status(.recording, elapsed: 60)))
        now += 14
        #expect(meeting.elapsed() == 74)
        #expect(MeetingModel.clock(meeting.elapsed()) == "1:14")
        meeting.apply(.meetingStatus(status(.writing, elapsed: 80)))
        now += 30
        #expect(meeting.elapsed() == 80)
        #expect(MeetingModel.clock(3725) == "1:02:05" && MeetingModel.length(1920) == "32 min")
        #expect(meeting.isCurrent("m1"))
        meeting.apply(.meetingStatus(status(.done, elapsed: 80)))
        #expect(!meeting.isCurrent("m1"))
    }

    @Test func theTranscriptFollowsUntilTheUserScrollsUpAndCountsWhatCameMeanwhile() {
        var follow = TranscriptFollow()
        let first = follow.arrived(2)
        #expect(first)
        follow.scrolled(distanceToEnd: 300)
        #expect(!follow.following)
        let (a, b) = (follow.arrived(2), follow.arrived(1))
        #expect(!a && !b)
        #expect(follow.unseen == 3)
        follow.jump()
        let after = follow.arrived(1)
        #expect(follow.following && follow.unseen == 0 && after)
        follow.scrolled(distanceToEnd: 400)
        follow.scrolled(distanceToEnd: 12)  // back at the end by hand
        #expect(follow.following)
    }

    @Test func addToRemindersMarksAtOnceAndAsksTheBrain() {
        let meeting = MeetingModel()
        var sent: [BrainCommand] = []
        meeting.send = { sent.append($0) }
        meeting.apply(.meetingNotes(MeetingNotes(id: "m1", title: "Sync", todos: [
            .init(text: "Write to the customer", mine: true), .init(text: "Slides", owner: "Anna"),
            .init(text: "Book the room", mine: true),
        ], reminders: true, mail: true)))
        meeting.addTodo("m1", 1)
        #expect(meeting.notes["m1"]?.todos.map(\.added) == [false, true, false])
        meeting.addTodo("m1")
        #expect(meeting.notes["m1"]?.todos.map(\.added) == [true, true, true])
        meeting.draftMail("m1")
        meeting.draftMail("m1")
        #expect(sent == [.meetingTodo(id: "m1", index: 1), .meetingTodo(id: "m1", index: -1), .meetingMail(id: "m1")])
    }

    @Test func copyPutsTheConsentLineAndTheNotesOnTheClipboard() {
        let meeting = MeetingModel()
        var copied: [String] = []
        meeting.copy = { copied.append($0) }
        meeting.copyConsent()
        meeting.apply(.meetingStatus(status(.recording)))
        meeting.copyConsent()
        meeting.apply(.meetingNotes(MeetingNotes(id: "m1", title: "Sync", markdown: "# Sync\n")))
        meeting.copyNotes("m1")
        #expect(copied == [MeetingModel.consent, "Milo is taking notes.", "# Sync\n"])
        #expect(meeting.copied && meeting.copiedNotes == "m1")
    }

    @Test func eachStepBringsItsBubbleAndButton() {
        let model = MiloModel(scheduler: ManualScheduler())
        var copied: [String] = []
        model.meeting.copy = { copied.append($0) }
        model.apply(.bubble("Taking notes. Stop me any time with the button next to me."))
        model.apply(.meetingStatus(status(.recording)))
        #expect(model.bubbleAction == .copyConsent)
        model.performBubbleAction()
        #expect(copied == ["Milo is taking notes."] && model.bubble == MiloModel.copiedConsent)

        model.apply(.meetingStatus(status(.recording, error: "I can't hear the others.", fix: .callAudio)))
        #expect(model.bubble == "I can't hear the others." && model.bubbleAction == .callAudio)
        model.apply(.meetingStatus(status(.recording, error: "I can't hear the others.", fix: .callAudio)))
        model.apply(.meetingStatus(status(.recording, elapsed: 70)))  // the same meeting again: no new bubble
        #expect(model.bubble == "I can't hear the others.")

        model.apply(.meetingStatus(status(.writing, step: "Writing the summary")))
        model.apply(.meetingStatus(status(.done, step: "Your notes from “Weekly sync” are ready.")))
        #expect(model.bubble == "Your notes from “Weekly sync” are ready." && model.bubbleAction == .openMeeting("m1"))
        var opened: [BubbleAction] = []
        model.onBubbleAction = { opened.append($0) }
        model.performBubbleAction()
        #expect(opened == [.openMeeting("m1")])
    }

    @Test func aQuestionWithItsOwnButtonsAnswersWithTheChoice() {
        let model = MiloModel(scheduler: ManualScheduler())
        var answers: [(String, Bool, String)] = []
        model.onAnswer = { answers.append(($0.id, $1, $2)) }
        let always = ConfirmChoice(id: "always", label: "Always for Zoom")
        model.apply(.confirm(id: "q", question: "Looks like a meeting. Should I take notes?", choices: [
            ConfirmChoice(id: "yes", label: "Take notes"), ConfirmChoice(id: "no", label: "Not this time"), always,
            ConfirmChoice(id: "never", label: "Never for Zoom"),
        ]))
        #expect(model.question?.choices.count == 4)
        model.answer(always)
        #expect(model.question == nil)
        #expect(answers.count == 1 && answers[0] == ("q", true, "always"))
        #expect(!ConfirmChoice(id: "never", label: "").yes && ConfirmChoice(id: "yes", label: "").yes)
    }

    /// What the brain sends through one meeting, as JSON lines, decoded and applied as the app does: the capsule
    /// shows, lines come in, the notes are written, then the page has them and the bubble opens them.
    @Test func aWholeMeetingFromTheWire() throws {
        let model = MiloModel(scheduler: ManualScheduler())
        let wire = [
            #"{"type":"meeting_status","id":"m1","phase":"recording","title":"Weekly sync","app":"Zoom","started":"2026-10-30T14:00:00","elapsed":0,"conversation":"c1","speakers":[],"consent":"Milo is taking notes for me."}"#,
            #"{"type":"meeting_lines","id":"m1","lines":[{"at":3.0,"end":8.0,"who":"You","me":true,"text":"Shall we start?"}],"reset":true}"#,
            #"{"type":"meeting_lines","id":"m1","lines":[{"at":9.5,"end":20.0,"who":"Speaker 2","me":false,"text":"Yes. The launch moves to Friday."}],"reset":false}"#,
            #"{"type":"meeting_status","id":"m1","phase":"writing","title":"Weekly sync","elapsed":1810,"conversation":"c1","speakers":["You","Anna"],"step":"Writing the summary"}"#,
            #"{"type":"meeting_lines","id":"m1","lines":[{"at":9.5,"end":20.0,"who":"Anna","me":false,"text":"Yes. The launch moves to Friday."}],"reset":false}"#,
            ##"{"type":"meeting_notes","id":"m1","title":"Weekly sync","duration":1810,"markdown":"# Weekly sync\n\n## Summary\n\nThe launch moves to Friday.\n","summary":"The launch moves to Friday.","todos":[{"text":"Write to the customer","owner":"","due":"","mine":true,"added":false}],"conversation":"c1","reminders":true}"##,
            #"{"type":"meeting_status","id":"m1","phase":"done","title":"Weekly sync","elapsed":1810,"conversation":"c1","speakers":["You","Anna"],"step":"Your notes from “Weekly sync” are ready. One to-do for you."}"#,
        ]
        let events = try wire.map { try JSONDecoder().decode(BrainEvent.self, from: Data($0.utf8)) }
        model.apply(events[0])
        #expect(model.meeting.status.live && model.bubbleAction == .copyConsent)
        model.apply(events[1])
        model.apply(events[2])
        #expect(model.meeting.lines["m1"]?.map(\.who) == ["You", "Speaker 2"])
        model.apply(events[3])
        #expect(model.meeting.status.phase == .writing && model.meeting.isCurrent("m1") && model.meeting.notes.isEmpty)
        model.apply(events[4])
        #expect(model.meeting.lines["m1"]?.map(\.who) == ["You", "Anna"])
        model.apply(events[5])
        model.apply(events[6])
        #expect(!model.meeting.isCurrent("m1"))
        #expect(model.meeting.notes["m1"]?.todos.first?.mine == true)
        #expect(NotesPage.blocks(model.meeting.notes["m1"]!.markdown) ==
                [.heading(level: 2, text: "Summary"), .paragraph("The launch moves to Friday.")])
        #expect(model.bubble == "Your notes from “Weekly sync” are ready. One to-do for you.")
        #expect(model.bubbleAction == .openMeeting("m1"))
    }
}

/// The notes renderer, on notes.md as brain/src/milo/services/meeting_text.py `render_notes` writes it.
@Suite struct MarkdownBlocksTests {
    static let notes = """
        # Weekly sync

        Thursday 30 October 2026, 14:00–14:30 · Zoom · with Anna

        ## Summary

        The launch moves to **Friday**. Anna
        sends the slides.

        ## Decisions

        - Launch on Friday
        - Keep the old login screen

        ## To-dos

        - [ ] You: Write to the customer (Friday)
        - [x] Anna: Send the slides

        ## Follow-up mail

        Hi Anna, thanks for today.

        [The whole transcript](transcript.md)

        """

    @Test func theSummarizersNotesBecomeBlocks() {
        #expect(MarkdownBlock.parse(Self.notes) == [
            .heading(level: 1, text: "Weekly sync"),
            .paragraph("Thursday 30 October 2026, 14:00–14:30 · Zoom · with Anna"),
            .heading(level: 2, text: "Summary"),
            .paragraph("The launch moves to **Friday**. Anna sends the slides."),
            .heading(level: 2, text: "Decisions"),
            .bullet("Launch on Friday", depth: 0),
            .bullet("Keep the old login screen", depth: 0),
            .heading(level: 2, text: "To-dos"),
            .todo(done: false, "You: Write to the customer (Friday)", depth: 0),
            .todo(done: true, "Anna: Send the slides", depth: 0),
            .heading(level: 2, text: "Follow-up mail"),
            .paragraph("Hi Anna, thanks for today."),
            .paragraph("[The whole transcript](transcript.md)"),
        ])
    }

    @Test func theNotesTabLeavesOutTheTitleTheDateAndTheToDos() {
        let blocks = NotesPage.blocks(Self.notes)
        #expect(blocks.first == .heading(level: 2, text: "Summary"))
        #expect(!blocks.contains { if case .todo = $0 { true } else { false } })
        #expect(blocks.contains(.heading(level: 2, text: "Follow-up mail")))
    }

    @Test func listsNumbersQuotesCodeAndRules() {
        let text = """
            1. First
            2) Second
               goes on here
              - nested
            > a quote
            > on two lines
            ---
            ```
            let x = 1
            ```
            #not a heading
            """
        #expect(MarkdownBlock.parse(text) == [
            .numbered(1, "First", depth: 0),
            .numbered(2, "Second goes on here", depth: 0),
            .bullet("nested", depth: 1),
            .quote("a quote on two lines"),
            .rule,
            .code("let x = 1"),
            .paragraph("#not a heading"),
        ])
    }

    @Test func inlineStylesParseAndBrokenOnesStayPlain() {
        let bold = MarkdownBlock.inline("The launch moves to **Friday**")
        #expect(String(bold.characters) == "The launch moves to Friday")
        #expect(bold.runs.contains { $0.inlinePresentationIntent == .stronglyEmphasized })
        #expect(String(MarkdownBlock.inline("a [b").characters) == "a [b")
    }

    @Test func onlyTheNotesOwnTranscriptLinkStaysALink() {
        let own = MarkdownBlock.inline("[The whole transcript](transcript.md)")
        #expect(own.runs.compactMap(\.link).map(\.relativeString) == ["transcript.md"])
        for text in ["[slides](https://example.com/x)", "[open](file:///Applications/Calculator.app)",
                     "[up](../../secret/transcript.md)", "[mail](mailto:a@b.c)", "<https://example.com>"] {
            let styled = MarkdownBlock.inline(text)
            #expect(styled.runs.allSatisfy { $0.link == nil }, "\(text) is still a link")
        }
        #expect(String(MarkdownBlock.inline("[slides](https://example.com/x)").characters) == "slides")
    }

    @Test func aMeetingConversationsPreviewLosesItsPrefix() {
        #expect(MeetingPageID.summary(of: "Notes from “Weekly sync”: The launch moves.") == "The launch moves.")
        #expect(MeetingPageID.summary(of: "Something else") == "Something else")
        #expect(MeetingPageID.firstSentence("One. Two.") == "One.")
        let info = ConversationInfo(id: "c", kind: .meeting, started: Date(), title: "x", source: "meeting:2026-10-30-x")
        #expect(MeetingPageID.meeting(of: info) == "2026-10-30-x")
    }
}
