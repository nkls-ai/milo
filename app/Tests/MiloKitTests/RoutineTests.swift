import Foundation
import Testing
@testable import MiloKit

@Suite struct RoutineTests {
    static let report = RoutineInfo(id: "monday-report", name: "Monday report", schedule: "every Monday at 09:00",
                                    lastRun: "2026-10-26 09:00, done", inputs: ["month"])
    static let draft = RoutineDraft(id: "d1", name: "Monday report", recipe: """
        ---
        name: Monday report
        inputs:
          - name: month
            ask: "Which month?"
            default: last month
          - name: folder
        schedule: every Monday at 09:00
        ---

        ## Steps

        1. Read the sales for {month}.
           Check: one row per day.
        """, schedule: "every Monday at 09:00")

    /// The controller too: it holds the model's buttons only weakly.
    private func controller() -> (MiloModel, FakeBrainClient, MiloController) {
        let brain = FakeBrainClient()
        let model = MiloModel(scheduler: ManualScheduler())
        let controller = MiloController(model: model, brain: brain, launcher: FakeBrainLauncher(),
                                        inserter: FakeTextInserter(), keys: FakeKeySource(),
                                        context: FakeContextProvider(), accessibility: FakeAccessibility(),
                                        scheduler: ManualScheduler())
        controller.start()
        brain.connect()
        return (model, brain, controller)
    }

    @Test func theModelKeepsTheRoutinesAndDraftsAndTheButtonsReachTheBrain() {
        let (model, brain, controller) = controller()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.routines([Self.report], drafts: [Self.draft]))
        #expect(model.routines == [Self.report] && model.drafts == [Self.draft])
        model.routine("monday-report", .run)
        model.routine("monday-report", .pause)
        model.answerDraft("d1", save: true)
        #expect(model.drafts.isEmpty, "a saved draft goes at once")
        #expect(brain.sent.contains(.routine(id: "monday-report", action: .run)))
        #expect(brain.sent.contains(.routine(id: "monday-report", action: .pause)))
        #expect(brain.sent.contains(.routineDraftAnswer(id: "d1", save: true)))
    }

    @Test func aDraftShowsItsStepsAndWhatItAsksEachTime() {
        #expect(Self.draft.steps.hasPrefix("## Steps\n\n1. Read the sales for {month}."))
        #expect(Self.draft.inputs == ["month: Which month? (last month)", "folder"])
        #expect(RoutineDraft(id: "x", name: "X", recipe: "just words").steps == "just words")
    }

    @Test func rowsSayWhenTheyRunAndHowTheLastRunWent() {
        #expect(RoutineRow.summary(Self.report) == "Every Monday at 09:00 · last run 2026-10-26 09:00, done")
        #expect(RoutineRow.summary(RoutineInfo(id: "t", name: "Tidy")) == "Only when you ask")
        #expect(RoutineRow.summary(RoutineInfo(id: "t", name: "T", schedule: "every day at 08:00", paused: true))
                == "Every day at 08:00, paused")
        #expect(RoutineRow.summary(RoutineInfo(id: "b", name: "b", problem: "It doesn't read.")) == "It doesn't read.")
    }

    @Test func theNextRoutineUpIsTheOneThatRunsFirst() throws {
        let soon = RoutineInfo(id: "a", name: "A", schedule: "x", nextRun: Date(timeIntervalSince1970: 100))
        let later = RoutineInfo(id: "b", name: "B", schedule: "x", nextRun: Date(timeIntervalSince1970: 200))
        let paused = RoutineInfo(id: "c", name: "C", schedule: "x", paused: true, nextRun: Date(timeIntervalSince1970: 50))
        #expect(RoutinesPanel.nextUp([later, paused, soon])?.id == "a")
        #expect(RoutinesPanel.nextUp([Self.report]) == nil)
        let now = try #require(RoutineInfo.parseTime("2026-10-30T12:00"))
        let monday = try #require(RoutineInfo.parseTime("2026-11-02T09:00"))
        #expect(RoutinesPanel.when(monday, now: now).hasPrefix("Monday at "))
    }

    @Test func aRoutineWithMissingFieldsStillDecodes() throws {
        let json = #"{"type":"routines","routines":[{"id":"x"}]}"#
        #expect(try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
                == .routines([RoutineInfo(id: "x", name: "x")], drafts: []))
    }
}
