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

    @Test func aClickOnTheMeetingCapsulesPauseOrStopIsTheirsNotMilos() async throws {
        // 2026-10-31: "the stop and pause button didn't work in the overlay": the capsule's row above Milo reaches
        // into his square, which took the press as a click on him.
        let model = MiloModel(scheduler: ManualScheduler())
        let panel = OverlayPanel(model: model)
        let host = try #require(panel.contentView as? DraggableHostingView<OverlayView>)
        model.meeting.apply(.meetingStatus(MeetingStatus(id: "m1", phase: .recording, title: "YouTube", app: "Safari",
                                                         elapsed: 60, conversation: "c1")))
        for _ in 0..<20 where model.meeting.area.isEmpty {
            host.layoutSubtreeIfNeeded()
            try await Task.sleep(for: .milliseconds(20))
        }
        let area = model.meeting.area
        #expect(!area.isEmpty, "the capsule says where it is")
        // Stop sits at the capsule's right end; low on it, where Milo's square begins.
        let stop = CGPoint(x: area.maxX - 16, y: OverlayPanel.size.height - (area.maxY - 6))
        func point(_ p: CGPoint) -> NSPoint { host.isFlipped ? NSPoint(x: p.x, y: host.bounds.maxY - p.y) : p }
        #expect(stop.y <= DraggableHostingView<OverlayView>.characterArea, "it is in his square: the case that broke")
        #expect(!host.isOnCharacter(point(stop)), "the press is Stop's")
        #expect(host.isOnCharacter(point(OverlayPanel.characterCenter)), "Milo himself still drags")
    }

    @Test func stopSitsInsideMilosSquareByHisSide() {
        let square = OverlayPanel.size.width - DraggableHostingView<OverlayView>.characterArea
        #expect(OverlayPanel.stopCenter.x > square && OverlayPanel.stopCenter.x < OverlayPanel.characterCenter.x - 40)
    }
}
