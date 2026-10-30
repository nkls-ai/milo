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
            .uiConfig(dictateKey: "fn", talkKey: "right_option", handsFreeMaxSeconds: 300),
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

    @Test func uiConfigWithoutHandsFreeCapKeepsTheDefault() throws {
        let json = #"{"type":"ui_config","dictate_key":"fn","talk_key":"right_option"}"#
        #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                == .uiConfig(dictateKey: "fn", talkKey: "right_option", handsFreeMaxSeconds: nil))
    }

    @Test func missingTypeThrows() {
        #expect(throws: DecodingError.self) {
            try JSONDecoder().decode(BrainEvent.self, from: Data(#"{"text":"hi"}"#.utf8))
        }
    }
}
