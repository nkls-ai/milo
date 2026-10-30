import Foundation
import Testing
@testable import MiloKit

@Suite struct TranscriptModelTests {
    let model = TranscriptModel()
    let date = Date(timeIntervalSince1970: 1_793_000_000)

    func user(_ id: String, _ text: String) -> TranscriptEntry {
        TranscriptEntry(id: id, date: date, kind: .user, text: text, via: .typed)
    }

    @Test func historyReplacesWhatWasThere() {
        model.apply(.entry(user("a", "old")))
        model.apply(.history([user("b", "one"), user("c", "two")]))
        #expect(model.entries.map(\.id) == ["b", "c"])
    }

    @Test func aReplyStreamsIntoItsEntryAndTheFinalEntryReplacesIt() {
        model.apply(.entry(TranscriptEntry(id: "m", date: date, kind: .milo, text: "", done: false)))
        model.apply(.replyDelta(id: "m", text: "Hello "))
        model.apply(.replyDelta(id: "m", text: "there."))
        #expect(model.entries.map(\.text) == ["Hello there."])
        #expect(model.entries[0].done == false)
        model.apply(.entry(TranscriptEntry(id: "m", date: date, kind: .milo, text: "Hello there.", emotion: .happy)))
        #expect(model.entries.count == 1 && model.entries[0].done && model.entries[0].emotion == .happy)
    }

    @Test func aDeltaForAnUnknownReplyStartsOne() {
        model.apply(.replyDelta(id: "x", text: "Hi"))
        #expect(model.entries.map(\.kind) == [.milo] && model.entries[0].done == false)
    }

    @Test func stepsAreAddedAndUpdatedInPlace() {
        model.apply(.entry(TranscriptEntry(id: "t", date: date, kind: .task, text: "Rename", status: .running)))
        model.apply(.activity(taskID: "t", step: ActivityStep(id: "1", kind: "read", title: "Reading a.txt",
                                                              status: .running)))
        model.apply(.activity(taskID: "t", step: ActivityStep(id: "2", kind: "edit", title: "Editing a.txt",
                                                              status: .running)))
        model.apply(.activity(taskID: "t", step: ActivityStep(id: "1", kind: "read", title: "Reading a.txt",
                                                              status: .failed)))
        #expect(model.entries[0].steps.map(\.status) == [.failed, .running])
        model.apply(.activity(taskID: "nope", step: ActivityStep(id: "1", kind: "x", title: "x", status: .done)))
        #expect(model.entries.count == 1)
    }

    @Test func keepsAtMostTheLimit() {
        for i in 0..<(TranscriptModel.limit + 5) { model.apply(.entry(user("\(i)", "turn \(i)"))) }
        #expect(model.entries.count == TranscriptModel.limit)
        #expect(model.entries.first?.id == "5")
    }

    @Test func emptyStateAndPendingRowsUseThePlainWords() {
        #expect(PendingRow.text(for: .thinking, last: nil) == "Thinking…")
        let streaming = TranscriptEntry(id: "m", date: date, kind: .milo, text: "Hi", done: false)
        #expect(PendingRow.text(for: .thinking, last: streaming) == nil)
        #expect(PendingRow.text(for: .idle, last: nil) == nil)
    }

    @Test func dayHeadingsOnlyWhenTheDayChanges() {
        let now = Date()
        #expect(DayHeading.text(for: now, after: nil) == "Today")
        #expect(DayHeading.text(for: now, after: now) == nil)
        #expect(DayHeading.text(for: now.addingTimeInterval(-86_400), after: nil) == "Yesterday")
    }
}
