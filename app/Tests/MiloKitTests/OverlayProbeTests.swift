import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// Puts the real overlay on screen, measures Milo's CPU at rest, asleep, listening and speaking, and flies him
/// to a point and back: `MILO_PROBE_DIR=/tmp/milo-probe swift test --filter OverlayProbe`. Takes about 2 minutes.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_PROBE_DIR"] != nil))
@MainActor
struct OverlayProbeTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_PROBE_DIR"] ?? "/tmp")

    @Test func idleCpuAndAFlight() throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        app.finishLaunching()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        pump(2)
        var report = ["baseline cpu without the overlay: \(String(format: "%.2f", cpu(over: 15)))%"]
        let model = MiloModel(scheduler: MainQueueScheduler())
        model.connected = true
        let panel = OverlayPanel(model: model)
        panel.placeBottomRight()
        panel.orderFrontRegardless()
        pump(1)
        report.append("visible: \(panel.occlusionState.contains(.visible))")

        pump(3)
        report.append("idle cpu: \(String(format: "%.2f", cpu(over: 30)))%")
        model.drowsy = true
        pump(4)
        report.append("asleep cpu: \(String(format: "%.2f", cpu(over: 20)))%")
        model.drowsy = false
        pump(2)
        // The brain sends the level about 20 times a second while he listens or speaks.
        for state in [MiloState.listening, .speaking] {
            model.apply(.state(state))
            var t = 0.0
            let voice = Timer(timeInterval: 0.05, repeats: true) { _ in
                t += 0.05
                let syllable = max(0, sin(t * 2 * .pi * 4.7) * 0.6 + sin(t * 2 * .pi * 2.3 + 1) * 0.4)
                MainActor.assumeIsolated { model.apply(.level(min(1, syllable * 0.9))) }
            }
            RunLoop.main.add(voice, forMode: .common)
            pump(1)
            if state == .speaking { try snapshot(panel, "probe-speaking") }
            report.append("\(state) cpu: \(String(format: "%.2f", cpu(over: 15)))%")
            voice.invalidate()
        }
        model.apply(.state(.idle))
        pump(2)

        let home = panel.frame.origin
        let primary = NSScreen.screens[0].frame
        let target = CGPoint(x: primary.width * 0.35, y: primary.height * 0.6)  // AppKit coordinates
        model.flyTarget = target
        var flights: [String] = []
        var origins: [NSPoint] = []
        for i in 0..<40 {
            pump(0.05)
            origins.append(panel.frame.origin)
            flights.append(describe(model.flight))
            if i == 10 { try snapshot(panel, "probe-flying") }
        }
        pump(0.5)
        try snapshot(panel, "probe-pointing")
        report.append("pointing cpu: \(String(format: "%.2f", cpu(over: 5)))%")
        let center = CGPoint(x: panel.frame.minX + OverlayPanel.characterCenter.x,
                             y: panel.frame.minY + OverlayPanel.characterCenter.y)
        let wanted = target
        report.append("target \(wanted), Milo's centre \(center), flight \(describe(model.flight))")
        report.append("path: " + origins.enumerated().filter { $0.offset % 5 == 0 }
            .map { "(\(Int($0.element.x)),\(Int($0.element.y)))" }.joined(separator: " "))
        report.append("phases: " + flights.reduce(into: [String]()) { if $0.last != $1 { $0.append($1) } }.joined(separator: " > "))

        model.flyTarget = nil
        pump(2)
        report.append("home again: \(panel.frame.origin == home), flight \(describe(model.flight))")
        panel.orderOut(nil)
        try report.joined(separator: "\n").write(to: dir.appendingPathComponent("probe.txt"), atomically: true, encoding: .utf8)
        #expect(panel.frame.origin == home)
    }

    /// Milliseconds for one frame of the live rig while he moves, and how many part images it redrew.
    @Test func frameCost() throws {
        _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 132, height: 132), styleMask: [.borderless],
                              backing: .buffered, defer: false)
        let view = WrenView(frame: NSRect(x: 0, y: 0, width: 132, height: 132))
        window.contentView = view
        view.layoutSubtreeIfNeeded()
        var lines: [String] = []
        for (name, make) in [("blink", { (i: Int) in FigureInput(pose: LifePose(blink: i % 2 == 0)) }),
                             ("speaking", { (i: Int) in FigureInput(state: .speaking, level: Double(i % 7) / 7) }),
                             ("turning", { (i: Int) in FigureInput(pose: LifePose(side: i % 2 == 0 ? -1 : 1)) })] {
            view.update(make(0))
            let redraws = view.redraws
            let began = Date()
            for i in 0..<300 {
                view.update(make(i / 10))
                view.step(1.0 / 60)
                CATransaction.flush()
            }
            let ms = Date().timeIntervalSince(began) / 300 * 1000
            lines.append(String(format: "%@: %.3f ms a frame, %.1f part images a frame", name, ms,
                                Double(view.redraws - redraws) / 300))
        }
        try lines.joined(separator: "\n").write(to: dir.appendingPathComponent("frame-cost.txt"), atomically: true, encoding: .utf8)
    }

    private func pump(_ seconds: TimeInterval) {
        RunLoop.main.run(until: Date().addingTimeInterval(seconds))
    }

    /// Percent of one core this process used while the overlay ran for `seconds`.
    private func cpu(over seconds: TimeInterval) -> Double {
        func used() -> Double {
            var r = rusage()
            getrusage(RUSAGE_SELF, &r)
            return Double(r.ru_utime.tv_sec + r.ru_stime.tv_sec) + Double(r.ru_utime.tv_usec + r.ru_stime.tv_usec) / 1e6
        }
        let start = used(), began = Date()
        pump(seconds)
        return (used() - start) / Date().timeIntervalSince(began) * 100
    }

    private func describe(_ flight: Flight) -> String {
        switch flight {
        case .perched: "perched"
        case .flying: "flying"
        case .pointing: "pointing"
        }
    }

    private func snapshot(_ panel: NSPanel, _ name: String) throws {
        guard let view = panel.contentView, let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { return }
        view.cacheDisplay(in: view.bounds, to: rep)
        try rep.representation(using: .png, properties: [:])?.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
