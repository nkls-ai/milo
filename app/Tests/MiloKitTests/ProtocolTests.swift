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
                      character: .pip),
            .history([
                TranscriptEntry(id: "5f2a9c1e04b7", date: try day("2026-10-30T09:12:03"), kind: .user,
                                text: "rename the photos from Friday", via: .voice),
                TranscriptEntry(id: "8d41e0a7c2f3", date: try day("2026-10-30T09:12:05"), kind: .milo,
                                text: "On it, I'll sort them by date.", emotion: .happy),
                TranscriptEntry(id: "c07b3e9d1a26", date: try day("2026-10-30T09:12:06"), kind: .task,
                                text: "Rename the photos from Friday in ~/Pictures by date taken", status: .done,
                                result: "I renamed all 40 photos.", steps: [
                                    ActivityStep(id: "item_1", kind: "read", title: "Looking in your Pictures folder",
                                                 detail: "ls ~/Pictures", status: .done),
                                ]),
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
            .confirmDone(id: "3b9e7a01c4d2", answer: "yes"),
            .appRequest(id: "a41f", op: "calendar.add_event", args: .object([
                "title": .string("Doctor"), "start": .string("2026-11-05T15:00:00"), "end": .string("2026-11-05T16:00:00"),
            ])),
            .handsBorrow(on: true, what: "mouse"),
        ])
    }

    private func day(_ text: String) throws -> Date {
        try #require(TranscriptEntry.parseDate(text))
    }

    @Test func everyCommandMatchesTheProtocolFile() throws {
        let commands: [BrainCommand] = [
            .listenStart(.dictate), .listenStart(.talk), .listenStart(.dictate, tentative: true), .listenConfirm,
            .listenStop, .listenCancel,
            .text("hello Milo"), .text("what's on today", speak: false), .getHistory,
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
            .appResponse(id: "a41f", outcome: .success(.object([
                "id": .string("E1F2-77"), "title": .string("Doctor"), "start": .string("2026-11-05T15:00:00"),
                "end": .string("2026-11-05T16:00:00"), "calendar": .string("Home"),
            ]))),
            .appResponse(id: "a42f", outcome: .failure(
                "Milo isn't allowed to use your calendar. Turn it on in System Settings › Privacy & Security › Calendars.")),
            .handsResult(id: "hands-7", ok: false, result: ["borrow": "mouse"],
                         error: "Excel doesn't take clicks in the background."),
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
        let json = #"{"type":"ui_config","dictate_key":"fn","talk_key":"right_option","character":"dragon"}"#
        #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                == .uiConfig(dictateKey: "fn", talkKey: "right_option", character: nil))
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

    @Test func missingTypeThrows() {
        #expect(throws: DecodingError.self) {
            try JSONDecoder().decode(BrainEvent.self, from: Data(#"{"text":"hi"}"#.utf8))
        }
    }
}
