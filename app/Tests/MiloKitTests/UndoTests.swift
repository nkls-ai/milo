import Foundation
import Testing
@testable import MiloKit

/// Undo on a finished task (ADR 0024): the button under the bubble that says what the task did, and on the task.
@Suite @MainActor struct UndoTests {
    static let red = UndoPoint(id: "t1", title: "Excel red", state: .ready, said: "Done: every cell of Book2 is red now.")

    private func connected() -> (MiloModel, FakeBrainClient, MiloController) {
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

    @Test func theBubbleThatSaysWhatATaskDidCarriesItsUndo() {
        let (model, brain, controller) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.undoPoints([Self.red]))
        brain.emit(.bubble("Done: every cell"))  // the words arrive piece by piece
        #expect(model.bubbleAction == .undo("t1"))
        brain.emit(.bubble("Done: every cell of Book2 is red now."))
        #expect(model.bubbleAction == .undo("t1"))
        model.performBubbleAction()
        #expect(brain.sent.contains(.undoTask(id: "t1")))
    }

    @Test func otherBubblesGetNoUndo() {
        let (model, brain, controller) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.undoPoints([Self.red]))
        brain.emit(.bubble("Your standup is at 10."))
        #expect(model.bubbleAction == nil)
        brain.emit(.undoPoints([UndoPoint(id: "t1", title: "Excel red", state: .undone, said: Self.red.said)]))
        brain.emit(.bubble(Self.red.said))
        #expect(model.bubbleAction == nil, "an undone task offers no Undo")
    }

    @Test func theButtonGoesOnceTheTaskIsBeingUndone() {
        let (model, brain, controller) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.undoPoints([Self.red]))
        brain.emit(.bubble(Self.red.said))
        model.performBubbleAction()
        brain.emit(.undoPoints([UndoPoint(id: "t1", title: "Excel red", state: .undoing, said: Self.red.said)]))
        #expect(model.bubbleAction == nil)
        #expect(model.bubble == Self.red.said, "what Milo said stays")
    }

    @Test func undoOnlyGoesForATaskThatCanBeUndone() {
        let (model, brain, controller) = connected()
        defer { withExtendedLifetime(controller) {} }
        brain.emit(.undoPoints([UndoPoint(id: "t2", title: "Rent", state: .undone)]))
        model.undo("t2")
        model.undo("nope")
        #expect(!brain.sent.contains { if case .undoTask = $0 { true } else { false } })
        brain.emit(.undoPoints([UndoPoint(id: "t2", title: "Rent", state: .ready)]))
        model.undo("t2")
        #expect(brain.sent.contains(.undoTask(id: "t2")))
        #expect(model.undoPoint("t2")?.title == "Rent")
    }

    @Test func aBubbleWithUndoStaysLongerThanOneWithout() {
        let scheduler = ManualScheduler()
        let model = MiloModel(scheduler: scheduler)
        model.apply(.undoPoints([Self.red]))
        model.show(Self.red.said)
        scheduler.advance(by: MiloModel.bubbleDuration(for: Self.red.said) + 1)
        #expect(model.bubble == Self.red.said)
        scheduler.advance(by: MiloModel.undoLinger)
        #expect(model.bubble == nil)
    }

    @Test func theUndoButtonKeepsPaceWithHisVoice() {
        #expect(BubbleAction.undo("t1").paced)
        #expect(!BubbleAction.permissions.paced)
        #expect(BubbleAction.undo("t1").title == "Undo")
    }
}
