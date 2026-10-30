import AppKit
import Testing
@testable import MiloKit

/// A long bubble grew the overlay panel down past the bottom of the screen, taking Milo and his Yes/No with
/// him (2026-10-30: a task's whole description, twice, as the question).
@MainActor
@Suite struct OverlayPanelSizeTests {
    @Test func aLongQuestionDoesNotGrowThePanel() {
        let model = MiloModel(scheduler: ManualScheduler())
        let panel = OverlayPanel(model: model)
        let long = String(repeating: "Open Microsoft Excel and make a new workbook with a simple table. ", count: 12)
        model.apply(.bubble(long))
        model.apply(.confirm(id: "q1", question: long + "?"))
        panel.alphaValue = 0  // laid out like on screen, without showing anything
        panel.orderFrontRegardless()
        defer { panel.orderOut(nil) }
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        panel.contentView?.layoutSubtreeIfNeeded()
        panel.layoutIfNeeded()
        #expect(panel.frame.size == OverlayPanel.size)
    }
}
