import Foundation
import Testing
@testable import MiloKit

@Suite struct HelperTests {
    static let working = HelperInfo(id: "h1", title: "Budget table in Excel", status: .working,
                                    step: "Typing “Monday” in Excel", progress: 0.4)

    @Test func theModelKeepsTheHelpersTheBrainSends() {
        let model = MiloModel(scheduler: ManualScheduler())
        model.apply(.helpers([Self.working]))
        #expect(model.helpers == [Self.working])
        model.apply(.helpers([]))
        #expect(model.helpers.isEmpty)
    }

    @Test func stopSendsStopHelperAndADroppedBrainTakesItsHelpersWithIt() {
        let brain = FakeBrainClient()
        let model = MiloModel(scheduler: ManualScheduler())
        let controller = MiloController(model: model, brain: brain, launcher: FakeBrainLauncher(),
                                        inserter: FakeTextInserter(), keys: FakeKeySource(),
                                        context: FakeContextProvider(), accessibility: FakeAccessibility(),
                                        scheduler: ManualScheduler())
        controller.start()
        brain.connect()
        brain.emit(.helpers([Self.working]))
        #expect(model.helpers == [Self.working])
        model.stopHelper("h1")
        #expect(brain.sent.contains(.stopHelper(id: "h1")))
        brain.connect(false)
        #expect(model.helpers.isEmpty)
    }

    @Test func clickingABirdOpensItsHelper() {
        let model = MiloModel(scheduler: ManualScheduler())
        var opened: [String] = []
        model.onOpenHelper = { opened.append($0) }
        model.openHelper("h1")
        #expect(opened == ["h1"])
    }

    @Test func eachStatusGetsItsOwnPerformance() {
        let looks: [(HelperInfo.Status, MiloState, Emotion, Bool, Bool)] = [
            (.working, .thinking, .thinking, false, false), (.queued, .idle, .neutral, true, false),
            (.needsYou, .idle, .neutral, false, true), (.done, .idle, .happy, false, false),
            (.failed, .idle, .concerned, false, false), (.stopped, .idle, .neutral, false, false),
        ]
        for (status, state, emotion, asleep, asking) in looks {
            let input = HelperBird.input(for: HelperInfo(id: "h1", title: "X", status: status))
            #expect((input.state, input.emotion, input.asleep, input.asking) == (state, emotion, asleep, asking), "\(status)")
            #expect(input.flight == .perched && input.connected)
        }
        #expect(HelperBird.input(for: Self.working, arriving: true).flight.airborne, "a new helper lands")
    }

    @Test func labelsBreakBetweenWords() {
        // six points a letter, a 48 point line: eight letters fit
        let measure = { (s: String) in CGFloat(s.count * 6) }
        #expect(HelperBird.label("Sort downloads by month", width: 48, measure: measure) == "Sort downloads…")
        #expect(HelperBird.label("Budget table", width: 48, measure: measure) == "Budget table")
        #expect(HelperBird.label("Dentist email to Dr Lee", width: 48, measure: measure) == "Dentist email…")
        #expect(!HelperBird.label("Sort downloads by month", width: 48, measure: measure).contains("downloa…"))
        #expect(HelperBird.label("", width: 48, measure: measure) == "")
    }

    @Test func onlyQueuedWorkingAndWaitingHelpersAreActive() {
        let active = [HelperInfo.Status.queued, .working, .needsYou, .done, .failed, .stopped].filter(\.active)
        #expect(active == [.queued, .working, .needsYou])
    }
}
