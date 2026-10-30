import AppKit
import QuartzCore
import SwiftUI
import Testing
@testable import MiloKit

/// How long from a key to the overlay showing it: the real overlay in an offscreen window, a fake key, and no
/// brain answering, so this is what the user sees before any round trip. Measures when SwiftUI has committed
/// the new look (what the next screen refresh shows) and checks that the drawing a frame later has changed: an
/// animated change starts from the old look, so its first frame can't differ yet.
/// Prints the medians; fails if one is slower than a frame, with room for a busy test machine.
@Suite(.serialized)
@MainActor
struct ResponseLatencyTests {
    /// One frame at 60 Hz.
    static let frame = 1.0 / 60
    /// A frame, with room for a test machine running other suites at the same time.
    static let limit = 2 * frame

    final class Rig {
        let brain = FakeBrainClient()
        let keys = FakeKeySource()
        let scheduler = ManualScheduler()
        let model: MiloModel
        let controller: MiloController
        let host: NSHostingView<AnyView>
        let window: NSWindow
        /// When the view tree last committed a new voice phase.
        var committed: (VoicePhase?, CFTimeInterval)?

        @MainActor init() {
            model = MiloModel(scheduler: scheduler)
            controller = MiloController(model: model, brain: brain, launcher: FakeBrainLauncher(),
                                        inserter: FakeTextInserter(), keys: keys, context: FakeContextProvider(),
                                        accessibility: FakeAccessibility(), scheduler: scheduler)
            controller.start()
            brain.connect()
            let size = OverlayPanel.size
            var report: (VoicePhase?) -> Void = { _ in }
            host = NSHostingView(rootView: AnyView(Probe(model: model) { report($0) }
                .frame(width: size.width, height: size.height)))
            host.frame = NSRect(origin: .zero, size: size)
            window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = host
            host.layoutSubtreeIfNeeded()
            report = { [unowned self] in committed = ($0, CACurrentMediaTime()) }
        }

        /// The pixels above Milo, where the bubble and the capsule are.
        @MainActor func snapshot() -> Data {
            let rect = NSRect(x: 0, y: 0, width: host.bounds.width, height: host.bounds.height - 160)
            guard let rep = host.bitmapImageRepForCachingDisplay(in: rect) else { return Data() }
            host.cacheDisplay(in: rect, to: rep)
            return rep.bitmapData.map { Data(bytes: $0, count: rep.bytesPerRow * rep.pixelsHigh) } ?? Data()
        }

        /// Seconds from `act` until the view tree shows `phase`, pumping the run loop as AppKit would, and whether
        /// the drawing a frame after that looks different.
        @MainActor func measure(_ phase: VoicePhase, _ act: () -> Void) -> (seconds: Double, drawn: Bool) {
            let before = snapshot()
            committed = nil
            let start = CACurrentMediaTime()
            act()
            while CACurrentMediaTime() - start < 1 {
                if let (seen, at) = committed, seen == phase {
                    RunLoop.main.run(until: Date().addingTimeInterval(ResponseLatencyTests.frame))
                    return (at - start, snapshot() != before)
                }
                RunLoop.main.run(until: Date().addingTimeInterval(0.0002))
            }
            return (.infinity, false)
        }

        @MainActor func settle() {
            RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        }
    }

    /// The overlay, telling the test when its voice phase changed.
    struct Probe: View {
        @ObservedObject var model: MiloModel
        let report: (VoicePhase?) -> Void

        var body: some View {
            OverlayView(model: model)
                .onChange(of: model.voicePhase) { report(model.voicePhase) }
        }
    }

    @Test func keysShowOnScreenWithinAFrame() {
        _ = NSApplication.shared
        var down: [Double] = [], held: [Double] = [], up: [Double] = []
        for round in 0..<7 {
            let rig = Rig()
            rig.settle()
            let t = Double(round) * 10
            let pressed = rig.measure(.armed(.talk)) { rig.keys.press(.rightOption, at: t) }
            rig.settle()
            let listening = rig.measure(.listening(.talk, handsFree: false)) { rig.scheduler.advance(by: 0.25) }
            rig.settle()
            let caught = rig.measure(.caught(.talk)) { rig.keys.release(.rightOption, at: t + 1) }
            #expect(pressed.drawn && listening.drawn && caught.drawn, "a change that wasn't drawn")
            down.append(pressed.seconds)
            held.append(listening.seconds)
            up.append(caught.seconds)
        }
        let medians = [("key down → light", down), ("hold confirmed → listening", held), ("key up → got it", up)]
            .map { ($0.0, Self.median($0.1)) }
        for (name, seconds) in medians {
            print("latency \(name): \(String(format: "%.2f", seconds * 1000)) ms to commit (one frame is 16.7 ms)")
            #expect(seconds < Self.limit, "\(name) took \(seconds * 1000) ms")
        }
    }

    static func median(_ values: [Double]) -> Double {
        let sorted = values.sorted()
        return sorted[sorted.count / 2]
    }
}
