import AppKit
import Testing
@testable import MiloKit

@MainActor @Suite struct StopByMiloTests {
    @Test func aClickOnStopIsTheButtonsNotADragOfMilo() throws {
        let model = MiloModel(scheduler: ManualScheduler())
        let panel = OverlayPanel(model: model)
        let host = try #require(panel.contentView as? DraggableHostingView<OverlayView>)
        // NSHostingView may be flipped: hand it points the way it reads them.
        func point(_ p: CGPoint) -> NSPoint { host.isFlipped ? NSPoint(x: p.x, y: host.bounds.maxY - p.y) : p }
        #expect(host.isOnCharacter(point(OverlayPanel.stopCenter)), "no Stop showing: it's Milo's square")
        model.apply(.state(.speaking))
        #expect(!host.isOnCharacter(point(OverlayPanel.stopCenter)), "Stop takes the click while he talks")
        #expect(host.isOnCharacter(point(OverlayPanel.characterCenter)), "Milo himself still drags")
    }

    @Test func stopSitsInsideMilosSquareByHisSide() {
        let square = OverlayPanel.size.width - DraggableHostingView<OverlayView>.characterArea
        #expect(OverlayPanel.stopCenter.x > square && OverlayPanel.stopCenter.x < OverlayPanel.characterCenter.x - 40)
    }
}
