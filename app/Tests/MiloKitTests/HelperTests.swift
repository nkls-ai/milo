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

    @Test func eachStatusGetsItsOwnLookOnTheSameCharacter() {
        let figure = HelperBird.figureModel(for: Self.working, character: .classic)
        #expect((figure.character, figure.state, figure.emotion, figure.drowsy) == (.classic, .thinking, .thinking, false))
        let looks: [(HelperInfo.Status, MiloState, Emotion, Bool)] = [
            (.queued, .idle, .neutral, true), (.needsYou, .idle, .concerned, false), (.done, .idle, .happy, false),
            (.failed, .idle, .confused, false), (.stopped, .idle, .neutral, false),
        ]
        for (status, state, emotion, drowsy) in looks {
            HelperBird.update(figure, for: HelperInfo(id: "h1", title: "X", status: status), character: .pip)
            #expect((figure.character, figure.state, figure.emotion, figure.drowsy) == (.pip, state, emotion, drowsy))
        }
        #expect(figure.connected)
    }

    @Test func onlyQueuedWorkingAndWaitingHelpersAreActive() {
        let active = [HelperInfo.Status.queued, .working, .needsYou, .done, .failed, .stopped].filter(\.active)
        #expect(active == [.queued, .working, .needsYou])
    }
}
