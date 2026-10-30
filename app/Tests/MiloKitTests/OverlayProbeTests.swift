import AppKit
import SwiftUI
import Testing
@testable import MiloKit

/// Puts the real overlay on screen, measures its idle CPU for Pip and the robot, and flies Pip to a point
/// and back: `MILO_PROBE_DIR=/tmp/milo-pip swift test --filter OverlayProbe`. Takes about 80 s.
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

        for style in CharacterStyle.allCases + [.pip] {
            model.character = style
            pump(3)
            report.append("\(style) idle cpu: \(String(format: "%.2f", cpu(over: 20)))%")
        }
        model.drowsy = true
        for style in CharacterStyle.allCases {
            model.character = style
            pump(3)
            report.append("\(style) asleep cpu: \(String(format: "%.2f", cpu(over: 15)))%")
        }
        model.drowsy = false
        model.character = .pip

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
        report.append("target \(wanted), Pip centre \(center), flight \(describe(model.flight))")
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

    /// Milliseconds to lay out and draw one frame of each figure, with something changing every frame.
    @Test func frameCost() throws {
        _ = NSApplication.shared
        func measure(_ make: (Int) -> AnyView) -> Double {
            let host = NSHostingView(rootView: make(0))
            host.frame = NSRect(x: 0, y: 0, width: 132, height: 132)
            let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
            window.contentView = host
            let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds)!
            for i in 0..<20 { host.rootView = make(i); host.cacheDisplay(in: host.bounds, to: rep) }
            let began = Date()
            for i in 0..<300 { host.rootView = make(i); host.cacheDisplay(in: host.bounds, to: rep) }
            return Date().timeIntervalSince(began) / 300 * 1000
        }
        let costs = CharacterStyle.allCases.map { style in
            let ms = measure { i in AnyView(CharacterFigure(for: style, pose: LifePose(lean: i % 2 == 0 ? 0 : 0.01), time: 0)) }
            return String(format: "%@ %.2f ms", style.rawValue, ms)
        }
        let line = "frame cost: " + costs.joined(separator: ", ")
        try line.write(to: dir.appendingPathComponent("frame-cost.txt"), atomically: true, encoding: .utf8)
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
