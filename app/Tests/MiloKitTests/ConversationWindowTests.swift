import Foundation
import Testing
@testable import MiloKit

/// The window's model of conversations: splits, opened ones, tasks finishing elsewhere, and a whole recorded session.
@Suite struct ConversationModelTests {
    let model = TranscriptModel()
    let date = Date(timeIntervalSince1970: 1_793_000_000)

    func entry(_ id: String, _ kind: TranscriptEntry.Kind, in conversation: String, _ text: String = "hi",
               status: ActivityStep.Status = .done) -> TranscriptEntry {
        TranscriptEntry(id: id, date: date, kind: kind, text: text, status: status, conversation: conversation)
    }

    func info(_ id: String, _ title: String, last: TimeInterval = 0, tasks: [TaskSummary] = []) -> ConversationInfo {
        ConversationInfo(id: id, started: date.addingTimeInterval(last), title: title, tasks: tasks)
    }

    @Test func aUserTurnInANewConversationStartsItAndKeepsTheOldOneOpened() {
        model.apply(.entry(entry("a1", .user, in: "c-a1")))
        model.apply(.entry(entry("a2", .milo, in: "c-a1")))
        #expect(model.current == "c-a1")
        model.apply(.entry(entry("b1", .user, in: "c-b1", "something else")))
        #expect(model.current == "c-b1")
        #expect(model.entries.map(\.id) == ["b1"])
        #expect(model.entries(of: "c-a1").map(\.id) == ["a1", "a2"])
    }

    @Test func theListSaysWhichConversationIsCurrent() {
        model.apply(.entry(entry("a1", .user, in: "c-a1")))
        model.apply(.conversations([info("c-b1", "B", last: 60), info("c-a1", "A")], current: "c-b1", more: true))
        #expect(model.current == "c-b1")
        #expect(model.more)
        #expect(model.entries.isEmpty)
        #expect(model.entries(of: "c-a1").map(\.id) == ["a1"])
    }

    @Test func aTaskFinishingInAnOlderConversationUpdatesItThere() {
        model.apply(.entry(entry("a1", .user, in: "c-a1")))
        model.apply(.entry(entry("t1", .task, in: "c-a1", "Rename", status: .running)))
        model.apply(.entry(entry("b1", .user, in: "c-b1")))
        model.apply(.activity(taskID: "t1", step: ActivityStep(id: "s", kind: "edit", title: "Renaming", status: .done)))
        #expect(model.task("t1")?.entry.steps.map(\.id) == ["s"])
        model.apply(.entry(entry("t1", .task, in: "c-a1", "Rename", status: .done)))
        #expect(model.entries.map(\.id) == ["b1"])
        #expect(model.task("t1")?.entry.status == .done)
        #expect(model.task("t1")?.conversation == nil)  // no headers yet
    }

    @Test func openingAConversationKeepsItsEntriesApart() {
        model.apply(.conversations([info("c-b1", "B", last: 60), info("c-a1", "A")], current: "c-b1", more: false))
        model.apply(.entry(entry("b1", .user, in: "c-b1")))
        model.apply(.conversation(info("c-a1", "A, renamed"), entries: [entry("a1", .user, in: "c-a1")]))
        #expect(model.current == "c-b1")
        #expect(model.entries.map(\.id) == ["b1"])
        #expect(model.entries(of: "c-a1").map(\.id) == ["a1"])
        #expect(model.info("c-a1")?.title == "A, renamed")
    }

    @Test func openingTheCurrentOneKeepsWhatIsStreaming() {
        model.apply(.entry(entry("a1", .user, in: "c-a1")))
        model.apply(.entry(TranscriptEntry(id: "a2", date: date.addingTimeInterval(1), kind: .milo, text: "Hel",
                                           done: false, conversation: "c-a1")))
        model.apply(.conversation(info("c-a1", "A"), entries: [entry("a1", .user, in: "c-a1")]))
        #expect(model.entries.map(\.id) == ["a1", "a2"])
    }

    @Test func aTaskIsFoundByItsConversationsHeaderBeforeItLoads() {
        let task = TaskSummary(id: "t9", title: "Report", status: .done, date: date)
        model.apply(.conversations([info("c-a1", "A", tasks: [task])], current: "", more: false))
        #expect(model.task("t9") == nil)
        #expect(model.conversation(ofTask: "t9")?.id == "c-a1")
    }

    @Test func searchResultsAndRemindersArriveAndClear() {
        model.apply(.searchResults(query: "photos", results: [SearchHit(conversation: "c-a1", title: "A", date: date)]))
        model.apply(.reminders([ReminderItem(due: date, text: "Call Anna")]))
        #expect(model.searchQuery == "photos" && model.searchResults.count == 1)
        #expect(model.reminders.map(\.text) == ["Call Anna"])
        model.clearSearch()
        #expect(model.searchQuery.isEmpty && model.searchResults.isEmpty)
    }

    /// protocol/conversations-session.jsonl is what a brain with a test MILO_HOME sent for a few turns and a helper
    /// task (brain/tests/services/test_conversations.py writes it). Replayed, the window has the right structure.
    @Test func aRecordedSessionGivesTheWindowItsStructure() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("protocol/conversations-session.jsonl")
        let lines = try String(contentsOf: url, encoding: .utf8).split(separator: "\n")
        let decoder = JSONDecoder()
        for line in lines {
            let event = try decoder.decode(BrainEvent.self, from: Data(line.utf8))
            if case let .unknown(type) = event { Issue.record("unknown event \(type)") }
            model.apply(event)
        }
        #expect(model.conversations.map(\.title) == ["Train to Hamburg", "Photos from Friday"])
        #expect(model.current == "c-000000000006")
        #expect(model.entries.map(\.text) == ["is my train to Hamburg on time", "The 8:12 is on time."])

        let photos = try #require(model.info("c-000000000001"))
        #expect(photos.titledBy == "milo")
        #expect(photos.turns == 2)
        #expect(photos.tasks.map(\.status) == [.done])
        let opened = model.entries(of: "c-000000000001")
        #expect(opened.map(\.kind) == [.user, .milo, .task, .user, .milo])
        let task = try #require(model.task("000000000003"))
        #expect(task.conversation?.id == "c-000000000001")
        #expect(task.entry.headline == "Rename Friday's photos")
        #expect(task.entry.steps.map(\.title) == ["Looking in your Pictures folder", "Renaming 40 photos"])
        #expect(task.entry.files == ["~/Pictures/renamed.txt"])
        #expect(model.reminders.map(\.text) == ["Leave for the dentist"])
    }
}

@Suite struct WindowRouteTests {
    @Test func goingDeeperSlidesForwardAndBackReturns() {
        let route = WindowRoute()
        route.go(.live)
        #expect(route.forward)
        route.go(.task("t1"))
        #expect(route.forward && route.page == .task("t1"))
        route.goBack()
        #expect(!route.forward && route.page == .live)
        route.goBack()
        #expect(route.page == .today)
        route.goBack()
        #expect(route.page == .today)
    }

    @Test func theSamePageIsNoMove() {
        let route = WindowRoute(page: .live)
        route.go(.live)
        #expect(route.back.isEmpty)
    }

    @Test func movingUpToTodaySlidesBack() {
        let route = WindowRoute(page: .conversation("c-a"))
        route.go(.today)
        #expect(!route.forward)
    }

    @Test func theWayBackIsBounded() {
        let route = WindowRoute()
        for i in 0..<30 { route.go(.conversation("c-\(i)")) }
        #expect(route.back.count == 20)
    }

    @Test func aPageNamesItsConversation() {
        let route = WindowRoute(page: .live)
        #expect(route.conversation(current: "c-a") == "c-a")
        #expect(route.conversation(current: "") == nil)
        route.go(.conversation("c-b"))
        #expect(route.conversation(current: "c-a") == "c-b")
        route.go(.today)
        #expect(route.conversation(current: "c-a") == nil)
    }
}

@Suite struct DayGroupsTests {
    var calendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "Europe/Berlin")!
        return c
    }

    func at(_ text: String) -> Date {
        let f = DateFormatter()
        f.calendar = calendar
        f.timeZone = calendar.timeZone
        f.dateFormat = "yyyy-MM-dd HH:mm"
        return f.date(from: text)!
    }

    func info(_ id: String, _ last: String) -> ConversationInfo {
        ConversationInfo(id: id, started: at(last), title: id)
    }

    @Test func conversationsFallIntoTodayYesterdayThisWeekAndMonths() {
        let now = at("2026-10-30 12:00")  // a Friday
        let list = [info("old", "2026-09-02 10:00"), info("tue", "2026-10-27 18:00"), info("now", "2026-10-30 09:00"),
                    info("thu", "2026-10-29 23:30"), info("fri", "2026-10-23 10:00")]
        let groups = DayGroups.group(list, now: now, calendar: calendar)
        #expect(groups.map(\.title) == ["Today", "Yesterday", "This week", "October", "September"])
        #expect(groups.map { $0.items.map(\.id) } == [["now"], ["thu"], ["tue"], ["fri"], ["old"]])
    }

    @Test func anotherYearSaysWhich() {
        let heading = DayGroups.heading(at("2025-12-24 10:00"), now: at("2026-10-30 12:00"), calendar: calendar)
        #expect(heading.contains("2025"))
    }

    @Test func rowTimesAreShortAndYesterdaySaysSo() {
        let now = at("2026-10-30 12:00")
        #expect(DayGroups.time(at("2026-10-29 08:00"), now: now, calendar: calendar) == "Yesterday")
        #expect(!DayGroups.time(at("2026-10-30 08:05"), now: now, calendar: calendar).isEmpty)
    }

    @Test func aConversationSubtitleSaysWhatItIs() {
        let now = Date()
        var info = ConversationInfo(id: "c", started: now, title: "Photos", via: [.message], turns: 3,
                                    tasks: [TaskSummary(id: "t", title: "Rename", status: .done, date: now)])
        let line = ConversationHeader.subtitle(info, now: now)
        #expect(line.hasPrefix("Today "))
        #expect(line.hasSuffix("3 turns · 1 task · from your phone"))
        info.kind = .meeting
        info.via = []
        info.tasks = []
        #expect(ConversationHeader.subtitle(info, now: now).hasSuffix("meeting notes"))
    }
}
