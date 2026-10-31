import Foundation
import Testing
@testable import MiloKit

/// A started controller; holding it keeps the controller alive for the test.
private final class Rig {
    let brain = FakeBrainClient()
    let scheduler = ManualScheduler()
    let model: MiloModel
    let controller: MiloController

    init(connections: AppConnections? = nil) {
        model = MiloModel(scheduler: scheduler)
        controller = MiloController(model: model, brain: brain, launcher: FakeBrainLauncher(),
                                    inserter: FakeTextInserter(), keys: FakeKeySource(),
                                    context: FakeContextProvider(), accessibility: FakeAccessibility(),
                                    scheduler: scheduler, connections: connections)
        controller.start()
        brain.clearSent()
    }
}

@Suite struct ConfirmAndConnectionsTests {
    private func controller(connections: AppConnections? = nil) -> (Rig, FakeBrainClient, MiloModel, ManualScheduler) {
        let rig = Rig(connections: connections)
        return (rig, rig.brain, rig.model, rig.scheduler)
    }

    @Test func aQuestionShowsUntilItIsOverAndAClickAnswersIt() {
        let (rig, brain, model, scheduler) = controller()
        brain.emit(.bubble("I'm about to run your shortcut. Go ahead?"))
        brain.emit(.confirm(id: "q1", question: "I'm about to run your shortcut. Go ahead?"))
        #expect(model.question == PendingQuestion(id: "q1", text: "I'm about to run your shortcut. Go ahead?"))
        scheduler.advance(by: 60)
        #expect(model.bubble != nil, "the bubble stays while Milo waits for an answer")
        model.answer(true)
        #expect(model.question == nil)
        #expect(brain.sent.last == .confirmAnswer(id: "q1", yes: true))
        brain.emit(.confirmDone(id: "q1", answer: "yes"))
        scheduler.advance(by: 30)
        #expect(model.bubble == nil)
        withExtendedLifetime(rig) {}
    }

    @Test func allowAlwaysIsSentOnlyWhereTheQuestionOfferedIt() {
        let (rig, brain, model, _) = controller()
        brain.emit(.confirm(id: "q1", question: "Replace 8 filled cells in “Budget”?", always: true))
        #expect(model.question?.always == true)
        model.answer(.always)
        #expect(brain.sent.last == .confirmAnswer(id: "q1", yes: true, always: true))
        brain.emit(.confirm(id: "q2", question: "Send it to Anna?"))
        model.answer(.always)  // no such button here: a plain yes
        #expect(brain.sent.last == .confirmAnswer(id: "q2", yes: true))
        brain.emit(.confirm(id: "q3", question: "Fill column C?", always: true))
        model.answer(.no)
        #expect(brain.sent.last == .confirmAnswer(id: "q3", yes: false))
        withExtendedLifetime(rig) {}
    }

    @Test func autoModeFollowsTheSettingsAndTheMenuTurnsItOff() {
        let (rig, brain, _, _) = controller()
        let ask = Setting(section: "approvals", key: "ask", value: "auto", options: ["step", "task", "auto"],
                          labels: ["Every step", "Once per task", "Only when it matters (auto)"], live: true)
        brain.emit(.settings(SettingsReport(settings: [ask])))
        #expect(rig.controller.autoMode)
        rig.controller.endAutoMode()
        #expect(brain.sent.last == .setSetting(section: "approvals", key: "ask", value: "task"))
        #expect(!rig.controller.autoMode, "shown off at once; the brain's report confirms it")
        withExtendedLifetime(rig) {}
    }

    @Test func removingAnAlwaysAllowedAppSendsTheListWithoutIt() {
        let excel: JSONValue = .object(["name": "Microsoft Excel", "bundle": ""])
        let numbers: JSONValue = .object(["name": "Numbers", "bundle": "com.apple.iWork.Numbers"])
        let apps = Setting(section: "approvals", key: "allowed_apps", value: .array([excel, numbers]), options: [],
                           labels: [], live: true)
        let settings = SettingsModel(report: SettingsReport(settings: [apps]))
        var sent: [BrainCommand] = []
        settings.send = { sent.append($0) }
        settings.change("approvals", "allowed_apps", to: .array([numbers]))
        #expect(sent == [.setSetting(section: "approvals", key: "allowed_apps", value: .array([numbers]))])
    }

    @Test func aSpokenAnswerOrTimeoutClearsTheQuestion() {
        let (rig, brain, model, _) = controller()
        brain.emit(.confirm(id: "q1", question: "Send it?"))
        brain.emit(.confirmDone(id: "other", answer: "no"))
        #expect(model.question != nil, "another question's end leaves this one")
        brain.emit(.confirmDone(id: "q1", answer: "timeout"))
        #expect(model.question == nil)
        #expect(brain.sent.isEmpty)
        withExtendedLifetime(rig) {}
    }

    @Test func appRequestsGoToTheConnectionsAndTheAnswerGoesBack() {
        let connections = FakeConnections()
        connections.outcome = .success(.array([.object(["title": .string("Dentist")])]))
        let (rig, brain, _, _) = controller(connections: connections)
        brain.emit(.appRequest(id: "a1", op: "calendar.events", args: .object(["start": .string("2026-11-02T00:00")])))
        #expect(connections.handled.map(\.op) == ["calendar.events"])
        #expect(brain.sent == [.appResponse(id: "a1", outcome: .success(.array([.object(["title": .string("Dentist")])])))])
        withExtendedLifetime(rig) {}
    }

    @Test func withoutConnectionsTheAppSaysSoPlainly() {
        let (rig, brain, _, _) = controller()
        brain.emit(.appRequest(id: "a1", op: "reminders.list", args: .object([:])))
        #expect(brain.sent == [.appResponse(id: "a1", outcome: .failure(MiloController.noConnections))])
        withExtendedLifetime(rig) {}
    }

    @Test func eventKitDatesAreLocalTimeLikeTheBrainWritesThem() throws {
        let date = try #require(EventKitConnections.date(.string("2026-11-05T15:00")))
        #expect(EventKitConnections.format(date) == "2026-11-05T15:00")
        #expect(EventKitConnections.date(.string("2026-11-05T15:00:30")) != nil)
        #expect(EventKitConnections.date(.string("next thursday")) == nil)
        #expect(EventKitConnections.date(nil) == nil)
    }

    @Test func anUnknownListNamesTheOnesThereAre() {
        #expect(EventKitConnections.noSuch("Shopping list", .reminder, among: ["Reminders", "Family"])
            == "There's no Reminders list called “Shopping list”. There are: Reminders, Family.")
        #expect(EventKitConnections.noSuch("Work", .event, among: []) == "There's no calendar called “Work”.")
    }

    @Test func jsonValuesRoundTrip() throws {
        let value: JSONValue = .object(["a": .array([.number(1), .bool(true), .null, .string("x")])])
        let back = try JSONDecoder().decode(JSONValue.self, from: JSONEncoder().encode(value))
        #expect(back == value)
    }
}
