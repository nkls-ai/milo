import Foundation
import Testing
@testable import MiloKit

/// protocol/messages.json at the repo root, found from this file's location.
private func loadMessages() throws -> [String: Any] {
    let url = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()  // MiloKitTests
        .deletingLastPathComponent()  // Tests
        .deletingLastPathComponent()  // app
        .deletingLastPathComponent()  // repo
        .appendingPathComponent("protocol/messages.json")
    let object = try JSONSerialization.jsonObject(with: Data(contentsOf: url))
    return try #require(object as? [String: Any])
}

private func entries(_ key: String) throws -> [[String: Any]] {
    try #require(try loadMessages()[key] as? [[String: Any]])
}

@Suite struct ProtocolTests {
    @Test func everyBrainMessageDecodesToAKnownEvent() throws {
        let decoder = JSONDecoder()
        let decoded = try entries("brain_to_app").map { entry in
            try decoder.decode(BrainEvent.self, from: JSONSerialization.data(withJSONObject: entry))
        }
        for event in decoded {
            if case let .unknown(type) = event { Issue.record("brain message type \(type) has no BrainEvent case") }
        }
        #expect(decoded == [
            .state(.idle), .state(.listening), .state(.dictating), .state(.transcribing),
            .state(.thinking), .state(.speaking),
            .emotion(.happy),
            .bubble("Hi Niklas! Your standup is at 10."),
            .heard("what's on my calendar"),
            .level(0.42),
            .dictation("Sounds good, ship it."),
            .status("Mic unavailable: no input device"),
            .partial("Sounds good, sh"),
            .uiConfig(dictateKey: "fn", talkKey: "right_option", handsFreeMaxSeconds: 300, whatsThisKey: "ctrl+option+m",
                      character: .milo, meetingKey: "ctrl+option+n"),
            .history([
                TranscriptEntry(id: "5f2a9c1e04b7", date: try day("2026-10-30T09:12:03"), kind: .user,
                                text: "rename the photos from Friday", via: .voice, conversation: "c-5f2a9c1e04b7"),
                TranscriptEntry(id: "8d41e0a7c2f3", date: try day("2026-10-30T09:12:05"), kind: .milo,
                                text: "On it, I'll sort them by date.", emotion: .happy, conversation: "c-5f2a9c1e04b7"),
                TranscriptEntry(id: "c07b3e9d1a26", date: try day("2026-10-30T09:12:06"), kind: .task,
                                text: "Rename the photos from Friday in ~/Pictures by date taken", status: .done,
                                result: "I renamed all 40 photos. The list is in ~/Pictures/Friday/renamed.txt.", steps: [
                                    ActivityStep(id: "item_1", kind: "read", title: "Looking in your Pictures folder",
                                                 detail: "ls ~/Pictures", status: .done),
                                ], conversation: "c-5f2a9c1e04b7", title: "Rename Friday's photos",
                                files: ["~/Pictures/Friday/renamed.txt"]),
            ]),
            .entry(TranscriptEntry(id: "e9a0f61b7d58", date: try day("2026-10-30T09:14:00"), kind: .milo, text: "",
                                   done: false)),
            .replyDelta(id: "e9a0f61b7d58", text: "Sure, "),
            .activity(taskID: "c07b3e9d1a26", step: ActivityStep(
                id: "item_2", kind: "edit", title: "Editing notes.md", detail: "update /Users/you/Milo/notes.md",
                status: .failed)),
            .lookRequest(id: "look-1", mode: "window"),
            .looking(true),
            .handsRequest(id: "hands-2", tool: "click", args: ["x": 640, "y": 412]),
            .handsSession(true),
            .flyTo(ScreenPoint(x: 812, y: 430.5)),
            .flyTo(nil),
            .confirm(id: "3b9e7a01c4d2", question: "I'm about to run your shortcut “Text Anna I'm late”. Go ahead?"),
            .confirm(id: "7c1d2e3f4a5b", question: "Looks like a meeting. Should I take notes?", choices: [
                ConfirmChoice(id: "yes", label: "Take notes"), ConfirmChoice(id: "no", label: "Not this time"),
                ConfirmChoice(id: "always", label: "Always for Zoom"), ConfirmChoice(id: "never", label: "Never for Zoom"),
            ]),
            .confirmDone(id: "3b9e7a01c4d2", answer: "yes"),
            .confirm(id: "5c1d2e3f4a5b", question: "Replace 8 filled cells in “Budget”?", always: true),
            .confirmDone(id: "5c1d2e3f4a5b", answer: "always"),
            .confirm(id: "7d8e9f0a1b2c", question: "I'm about to click “Buy Now” in Safari. Go ahead?", money: true),
            .confirmDone(id: "7d8e9f0a1b2c", answer: "no"),
            .appRequest(id: "a41f", op: "calendar.add_event", args: .object([
                "title": .string("Doctor"), "start": .string("2026-11-05T15:00:00"), "end": .string("2026-11-05T16:00:00"),
            ])),
            .helpers([
                HelperInfo(id: "c0ffee12ab34", title: "Budget table in Excel", status: .working,
                           step: "Typing “Monday” in Excel", progress: 0.4),
                HelperInfo(id: "d00d12ab3456", title: "Flights to Lisbon", status: .queued, step: "Waiting for a free helper"),
                HelperInfo(id: "e1e1e1e1e1e1", title: "Sort downloads", status: .needsYou, step: "Waiting for your answer"),
                HelperInfo(id: "f2f2f2f2f2f2", title: "Dentist email", status: .done),
            ]),
            .undoPoints([
                UndoPoint(id: "f2f2f2f2f2f2", title: "Excel red", state: .ready, said: "Done: every cell of Book2 is red now."),
                UndoPoint(id: "a1b2c3d4e5f6", title: "Rent 950", state: .undone, said: "I changed the rent to 950."),
                UndoPoint(id: "b2c3d4e5f6a7", title: "Letter to Anna", state: .undoing),
            ]),
            .actionDone(ActionDone(kind: "event", title: "Dentist", detail: "Thursday 5 November, 15:00 to 16:00",
                                   when: "2026-11-05T15:00", app: "Calendar", undo: "q-3f9a2c7d1e04")),
            .actionDone(ActionDone(kind: "shortcut", title: "Lights off")),
            .handsBorrow(on: true, what: "mouse"),
            .access(AccessNote(need: .control, state: .ask,
                               text: "macOS will ask once whether I may use Microsoft Excel. Click Allow.", app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel"))),
            .access(AccessNote(need: .control, state: .no,
                               text: "Okay, I won't use Microsoft Excel. If you change your mind, Fix it shows the switch.",
                               app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel"))),
            .access(AccessNote(need: .ui, state: .no,
                               text: "To work in other apps' windows I need Accessibility. Fix it shows where to switch it on.")),
            .appRequest(id: "a43f", op: "calendar.update_event", args: .object([
                "id": .string("E1F2-77"), "at": .string("2026-11-05T15:00"), "start": .string("2026-11-06T10:00"),
                "end": .string("2026-11-06T11:00"),
            ])),
            .appRequest(id: "a44f", op: "media.pause", args: .object([:])),
            .appRequest(id: "a51f", op: "access.check", args: .object([
                "need": .string("control"), "app": .string("Microsoft Excel"), "bundle": .string(""), "launch": .bool(true),
            ])),
            .appRequest(id: "a52f", op: "access.request", args: .object([
                "need": .string("control"), "app": .string("Microsoft Excel"), "bundle": .string("com.microsoft.Excel"),
            ])),
            .appRequest(id: "a53f", op: "access.places", args: .object([
                "app": .string("Microsoft Excel"), "bundle": .string("com.microsoft.Excel"),
            ])),
            .facts([
                MemoryFact(id: "01JBF6Z3Q8M2X4K7N9P0R5T6VW", text: "The user's name is Niklas.", topic: "basics",
                           since: "2026-10-30T09:12:00", pinned: true),
                MemoryFact(id: "01JBF7A1B2C3D4E5F6G7H8J9KM", text: "Anna is the user's sister. Her birthday is March 3.",
                           topic: "people", since: "2026-10-30T18:05:41"),
            ]),
            .routines([
                RoutineInfo(id: "monday-report", name: "Monday report",
                            description: "Sums last week's sales into a one-page report.",
                            schedule: "every Monday at 09:00", lastRun: "2026-10-26 09:00, done",
                            nextRun: try #require(RoutineInfo.parseTime("2026-11-02T09:00")), inputs: ["month"]),
                RoutineInfo(id: "tidy-downloads", name: "Tidy downloads", paused: true),
                RoutineInfo(id: "broken", name: "broken", problem: "it must start with a line of three dashes (---)"),
            ], drafts: [
                RoutineDraft(id: "d4e5f6a7", name: "Invoice folder", recipe: """
                    ---
                    name: Invoice folder
                    schedule:
                    paused: no
                    version: 1
                    ---

                    ## Steps

                    1. Move this month's invoices from Downloads into Invoices.
                       Check: Downloads has no invoice left.

                    """),
            ]),
            .settings(SettingsReport(settings: [
                Setting(section: "ui", key: "voice", value: true),
                Setting(section: "chat", key: "updates", value: "bubble", options: ["quiet", "bubble", "chatty"],
                        labels: ["Only the answer", "Short notes in his bubble", "Tells you each step"]),
                Setting(section: "dictation", key: "stream", value: "preview", options: ["off", "preview", "type"],
                        labels: ["When you let go", "Show the words as you speak", "Type as you speak"]),
            ])),
            .settings(SettingsReport(settings: [], error: "The dictate key and the talk key need to be different keys.")),
            .usage(UsageReport(span: 3, today: "2026-10-30", since: "2026-10-29", daily: [
                UsageDay(day: "2026-10-28"),
                UsageDay(day: "2026-10-29", calls: 4, inputTokens: 61200, cachedInputTokens: 38400, outputTokens: 210,
                         dictations: 12, words: 148),
                UsageDay(day: "2026-10-30", calls: 9, inputTokens: 84050, cachedInputTokens: 70100, outputTokens: 655,
                         dictations: 31, words: 402),
            ], sources: [UsageSource(source: "task", calls: 2, tokens: 98000),
                         UsageSource(source: "chat", calls: 11, tokens: 48115)],
            apps: [UsageApp(app: "Slack", dictations: 20, words: 310), UsageApp(app: "Mail", dictations: 23, words: 240)],
            accounts: [
                UsageAccount(service: "Claude", uses: ["Talking"], plan: "Max", who: "you@example.com",
                             detail: "claude-haiku-5-5"),
                UsageAccount(service: "ChatGPT", uses: ["Tasks"], detail: "Signed in with ChatGPT"),
                UsageAccount(service: "ElevenLabs", uses: ["Milo's voice", "Hearing you"], state: .unknown,
                             detail: "Can't see the plan: the API key lacks the user_read permission."),
                UsageAccount(service: "This Mac", uses: ["Dictation"], state: .local,
                             detail: "Whisper, nothing leaves the Mac"),
            ])),
            .remote(RemoteStatus(channel: "telegram", label: "Telegram", state: .paired, detail: "Niklas (@niklas)")),
            .remote(RemoteStatus(channel: "telegram", label: "Telegram", state: .unpaired,
                                 detail: "Message @milo_mac_bot from your phone to connect.")),
            .meetingRecord(id: "2026-10-30-1400-weekly-sync",
                           dir: "/Users/you/Milo/meetings/2026-10-30-1400-weekly-sync/audio", on: true),
            .meetingStatus(MeetingStatus(
                id: "2026-10-30-1400-weekly-sync", phase: .recording, title: "Weekly sync", app: "Zoom",
                started: try day("2026-10-30T14:00:12"), elapsed: 754.2, conversation: "c-7d6e5f4a3b2c",
                speakers: ["You", "Anna", "Speaker 2"],
                error: "I can only hear you, not the others. Turn on System Audio Recording for Milo in System Settings › Privacy & Security.",
                fix: .callAudio, consent: "Milo is taking notes for me. They stay on my computer.")),
            .meetingStatus(MeetingStatus(
                id: "2026-10-30-1400-weekly-sync", phase: .writing, title: "Weekly sync", app: "Zoom",
                started: try day("2026-10-30T14:00:12"), elapsed: 1810, conversation: "c-7d6e5f4a3b2c",
                speakers: ["You", "Anna"], step: "Writing the summary",
                consent: "Milo is taking notes for me. They stay on my computer.")),
            .meetingStatus(MeetingStatus()),
            .meetingLines(id: "2026-10-30-1400-weekly-sync", lines: [
                MeetingLine(at: 1.2, end: 4.8, who: "Anna", text: "Shall we move the launch to Friday?"),
                MeetingLine(at: 5.4, end: 7.1, who: "You", me: true, text: "Friday works for me."),
            ], reset: false),
            .meetingNotes(MeetingNotes(
                id: "2026-10-30-1400-weekly-sync", title: "Weekly sync", started: try day("2026-10-30T14:00:12"),
                duration: 1810, markdown: """
                    # Weekly sync

                    Thursday 30 October 2026, 14:00–14:30 · Zoom · with Anna

                    ## Summary

                    The launch moves to Friday.

                    ## Decisions

                    - Launch on Friday

                    ## To-dos

                    - [ ] You: Write to the customer (Friday)
                    - [ ] Anna: Send the slides

                    [The whole transcript](transcript.md)

                    """,
                summary: "The launch moves to Friday.", decisions: ["Launch on Friday"], todos: [
                    MeetingNotes.Todo(text: "Write to the customer", due: "Friday", mine: true),
                    MeetingNotes.Todo(text: "Send the slides", owner: "Anna", added: true),
                ], followup: "Hi Anna, thanks for today.", people: ["Anna"], app: "Zoom",
                conversation: "c-7d6e5f4a3b2c", folder: "/Users/you/Milo/meetings/2026-10-30-1400-weekly-sync",
                reminders: true, mail: true)),
            .conversations([
                ConversationInfo(id: "c-5f2a9c1e04b7", started: try day("2026-10-30T09:12:03"),
                                 last: try day("2026-10-30T09:14:10"), title: "Photos from Friday", via: [.voice],
                                 turns: 1, preview: "I renamed all 40 photos.", tasks: [
                                     TaskSummary(id: "c07b3e9d1a26", title: "Rename Friday's photos", status: .done,
                                                 date: try day("2026-10-30T09:12:06")),
                                 ]),
                ConversationInfo(id: "c-1b2c3d4e5f60", started: try day("2026-10-30T07:40:00"),
                                 last: try day("2026-10-30T07:41:12"), title: "Train to Hamburg", titledBy: "words",
                                 via: [.message], turns: 2, preview: "The 8:12 is on time."),
                ConversationInfo(id: "c-a0b1c2d3e4f5", kind: .routine, started: try day("2026-10-27T09:00:00"),
                                 last: try day("2026-10-27T09:03:40"), title: "Monday report", titledBy: "words",
                                 preview: "The report is in Reports.", tasks: [
                                     TaskSummary(id: "a0b1c2d3e4f5", title: "Monday report", status: .done,
                                                 date: try day("2026-10-27T09:00:00")),
                                 ], source: "routine:Monday report"),
                ConversationInfo(id: "c-9e8d7c6b5a40", kind: .meeting, started: try day("2026-10-29T15:02:11"),
                                 title: "Weekly sync", titledBy: "words",
                                 preview: "Notes from “Weekly sync”: Launch moves to Friday.",
                                 source: "meeting:2026-10-29-1400-weekly-sync"),
            ], current: "c-5f2a9c1e04b7", more: false),
            .conversation(ConversationInfo(id: "c-1b2c3d4e5f60", started: try day("2026-10-30T07:40:00"),
                                           last: try day("2026-10-30T07:41:12"), title: "Train to Hamburg",
                                           titledBy: "words", via: [.message], turns: 2,
                                           preview: "The 8:12 is on time."), entries: [
                TranscriptEntry(id: "1b2c3d4e5f60", date: try day("2026-10-30T07:40:00"), kind: .user,
                                text: "is my train to Hamburg on time", via: .message, conversation: "c-1b2c3d4e5f60"),
                TranscriptEntry(id: "2c3d4e5f6071", date: try day("2026-10-30T07:41:12"), kind: .milo,
                                text: "The 8:12 is on time.", emotion: .happy, conversation: "c-1b2c3d4e5f60"),
            ]),
            .searchResults(query: "photos", results: [
                SearchHit(conversation: "c-5f2a9c1e04b7", title: "Photos from Friday", date: try day("2026-10-30T09:12:03"),
                          snippet: "rename the photos from Friday", via: [.voice]),
            ]),
            .reminders([
                ReminderItem(due: try #require(RoutineInfo.parseTime("2026-10-30T15:30")), text: "Leave for the dentist"),
                ReminderItem(due: try #require(RoutineInfo.parseTime("2026-10-31T09:00")), text: "Call Anna"),
            ]),
        ])
    }

    private func day(_ text: String) throws -> Date {
        try #require(TranscriptEntry.parseDate(text))
    }

    @Test func everyCommandMatchesTheProtocolFile() throws {
        let commands: [BrainCommand] = [
            .listenStart(.dictate), .listenStart(.talk), .listenStart(.dictate, tentative: true), .listenConfirm,
            .listenStop, .listenCancel,
            .text("hello Milo"), .text("what's on today", speak: false),
            .text("and what about the other one?", speak: false, conversation: "c-1b2c3d4e5f60"), .getHistory,
            .getConversations(before: ""), .getConversations(before: "2026-10-01T00:00:00"),
            .openConversation(id: "c-1b2c3d4e5f60"), .searchConversations(query: "dentist"),
            .renameConversation(id: "c-1b2c3d4e5f60", title: "Hamburg trip"), .newConversation,
            .context(app: "Xcode", idleSeconds: 3.5), .mute(true),
            .lookResult(id: "look-1", ScreenCapture(
                app: "Microsoft Excel", window: "Budget.xlsx", focused: "cell C4: =SUM(C1:C3)", text: "Rent 900\nFood 320",
                image: "/Users/you/Milo/state/screens/look-20261030-091400.png")),
            .lookResult(id: "look-4", ScreenCapture(
                app: "Safari",
                error: "I can't take screenshots yet. Turn on Screen Recording for Milo in System Settings › Privacy & Security.")),
            .whatsThis(ScreenCapture(app: "Mail", selection: "Your parcel is waiting. Pay 1.99 EUR customs here.")),
            .handsResult(id: "hands-2", ok: true, result: ["text": "Clicked."]),
            .handsResult(id: "hands-5", ok: false, result: [:], error: "There is no element e99. Call ax_tree again."),
            .handsStop(reason: "escape"),
            .confirmAnswer(id: "3b9e7a01c4d2", yes: true),
            .confirmAnswer(id: "5c1d2e3f4a5b", yes: true, always: true),
            .confirmAnswer(id: "7c1d2e3f4a5b", yes: true, choice: "always"),
            .appResponse(id: "a41f", outcome: .success(.object([
                "id": .string("E1F2-77"), "title": .string("Doctor"), "start": .string("2026-11-05T15:00:00"),
                "end": .string("2026-11-05T16:00:00"), "calendar": .string("Home"),
            ]))),
            .appResponse(id: "a42f", outcome: .failure(
                "Milo isn't allowed to use your calendar. Turn it on in System Settings › Privacy & Security › Calendars.")),
            .appResponse(id: "a44f", outcome: .success(.object(["state": .string("paused")]))),
            .appResponse(id: "a51f", outcome: .success(.object([
                "access": .string("ask"), "app": .string("Microsoft Excel"), "bundle": .string("com.microsoft.Excel"),
                "system": .string("macOS"), "button": .string("Allow"),
            ]))),
            .appResponse(id: "a52f", outcome: .success(.object([
                "access": .string("no"), "app": .string("Microsoft Excel"), "bundle": .string("com.microsoft.Excel"),
                "system": .string("macOS"),
            ]))),
            .appResponse(id: "a53f", outcome: .success(.object([
                "sandboxed": .bool(true), "places": .array([.string("/Users/you/Library/Containers/com.microsoft.Excel/Data")]),
            ]))),
            .stopHelper(id: "c0ffee12ab34"),
            .undoTask(id: "f2f2f2f2f2f2"),
            .stopAll,
            .handsResult(id: "hands-7", ok: false, result: ["borrow": "mouse"],
                         error: "Excel doesn't take clicks in the background."),
            .getFacts, .forgetFact(id: "01JBF7A1B2C3D4E5F6G7H8J9KM"),
            .editFact(id: "01JBF7A1B2C3D4E5F6G7H8J9KM", text: "Anna is the user's sister. Her birthday is March 4."),
            .routine(id: "monday-report", action: .run),
            .routine(id: "tidy-downloads", action: .resume),
            .routineDraftAnswer(id: "d4e5f6a7", save: true),
            .getSettings,
            .getUsage(span: 30),
            .setSetting(section: "ui", key: "voice", value: true),
            .setSetting(section: "ui", key: "voice", value: false),
            .remotePause(true), .remoteForget,
            .callStarted(app: "Zoom", bundle: "us.zoom.xos", title: "Zoom Meeting"),
            .callEnded(app: "Zoom"),
            .meetingChunk(MeetingChunk(
                id: "2026-10-30-1400-weekly-sync", track: "them", index: 3,
                path: "/Users/you/Milo/meetings/2026-10-30-1400-weekly-sync/audio/them-0003.wav", start: 60, seconds: 30)),
            .meetingRecording(id: "2026-10-30-1400-weekly-sync", on: true, tracks: ["me"],
                              error: "I can only hear you, not the others. Turn on System Audio Recording for Milo in System Settings › Privacy & Security."),
            .meetingToggle(false),
            .meetingPause(true),
            .openMeeting(id: "2026-10-30-1400-weekly-sync"),
            .meetingTodo(id: "2026-10-30-1400-weekly-sync", index: 0),
            .meetingTodo(id: "2026-10-30-1400-weekly-sync", index: -1),
            .meetingMail(id: "2026-10-30-1400-weekly-sync"),
            .dictationFixed([DictationFix(heard: "Cloud Code", meant: "Claude Code"),
                             DictationFix(heard: "Nicholas", meant: "Niklas")]),
        ]
        let encoder = JSONEncoder()
        let encoded = try commands.map { command in
            try #require(try JSONSerialization.jsonObject(with: encoder.encode(command)) as? NSDictionary)
        }
        let expected = try entries("app_to_brain").map { $0 as NSDictionary }
        for entry in expected where !encoded.contains(entry) {
            Issue.record("no BrainCommand encodes to \(entry)")
        }
        for (command, object) in zip(commands, encoded) where !expected.contains(object) {
            Issue.record("\(command) encodes to \(object), which protocol/messages.json doesn't list")
        }
    }

    @Test func unknownTypeDecodesToUnknown() throws {
        let event = try JSONDecoder().decode(BrainEvent.self, from: Data(#"{"type":"confetti","n":3}"#.utf8))
        #expect(event == .unknown("confetti"))
    }

    @Test func unknownStateAndEmotionFallBack() throws {
        let decoder = JSONDecoder()
        #expect(try decoder.decode(BrainEvent.self, from: Data(#"{"type":"state","state":"dancing"}"#.utf8)) == .state(.idle))
        #expect(try decoder.decode(BrainEvent.self, from: Data(#"{"type":"emotion","emotion":"smug"}"#.utf8)) == .emotion(.neutral))
    }

    @Test func uiConfigWithAnUnknownCharacterDecodesAsNone() throws {
        let json = #"{"type":"ui_config","dictate_key":"fn","talk_key":"right_option","character":"unicorn"}"#
        #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                == .uiConfig(dictateKey: "fn", talkKey: "right_option", character: nil))
    }

    @Test func aRetiredLookFromAnOldConfigMeansMilo() throws {
        for name in ["pip", "classic", "dragon", "kit", "glow", "milo"] {
            let json = #"{"type":"ui_config","dictate_key":"fn","talk_key":"right_option","character":"\#(name)"}"#
            #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                    == .uiConfig(dictateKey: "fn", talkKey: "right_option", character: .milo))
        }
    }

    @Test func uiConfigWithoutHandsFreeCapKeepsTheDefault() throws {
        let json = #"{"type":"ui_config","dictate_key":"fn","talk_key":"right_option"}"#
        #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                == .uiConfig(dictateKey: "fn", talkKey: "right_option", handsFreeMaxSeconds: nil))
    }

    @Test func handsRequestArgsKeepTheirJSONShape() throws {
        let json = #"{"type":"hands_request","id":"h","tool":"key","args":{"combo":"cmd+s","n":[1,true,null]}}"#
        let event = try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
        #expect(event == .handsRequest(id: "h", tool: "key",
                                       args: ["combo": "cmd+s", "n": .array([1, true, .null])]))
    }

    @Test func aHelperWithAnUnknownStatusShowsAsWorkingAndProgressStaysInRange() throws {
        let json = #"{"type":"helpers","helpers":[{"id":"h","title":"X","status":"dreaming","step":"","progress":3}]}"#
        #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                == .helpers([HelperInfo(id: "h", title: "X", status: .working, progress: 1)]))
    }

    @Test func missingTypeThrows() {
        #expect(throws: DecodingError.self) {
            try JSONDecoder().decode(BrainEvent.self, from: Data(#"{"text":"hi"}"#.utf8))
        }
    }
}

@Suite struct RemoteStatusTests {
    @Test func theMenuLineSaysWhereThingsStand() {
        var status = RemoteStatus(channel: "telegram", label: "Telegram", state: .paired, detail: "Niklas")
        #expect(status.summary == "Telegram: connected (Niklas)")
        status.paused = true
        #expect(status.summary == "Telegram: paused (Niklas)")
        #expect(RemoteStatus(channel: "imessage", label: "iMessage", state: .unpaired).summary
            == "iMessage: no phone connected yet")
        #expect(RemoteStatus(channel: "telegram", label: "Telegram", state: .error, detail: "bad token").summary
            == "Telegram: not working")
    }

    @Test func theModelKeepsTheLastStatusAndAMessageTurnShowsAPhone() throws {
        let model = MiloModel(scheduler: ManualScheduler())
        #expect(model.remote == nil)
        let status = RemoteStatus(channel: "telegram", label: "Telegram", state: .paired)
        model.apply(.remote(status))
        #expect(model.remote == status)
        let entry = try JSONDecoder().decode(TranscriptEntry.self, from: Data("""
            {"id": "a", "ts": "2026-10-30T09:12:03", "kind": "user", "text": "hi", "via": "message"}
            """.utf8))
        #expect(entry.via == .message)
    }
}
