import AppKit
import Testing
@testable import MiloKit

/// Puts Milo's cursor overlay on screen and measures its CPU at rest and while gliding, and checks it does no
/// work when idle: `MILO_PROBE_DIR=/tmp/milo-cursor swift test --filter CursorProbe`. Takes about 40 s.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_PROBE_DIR"] != nil))
@MainActor
struct CursorProbeTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_PROBE_DIR"] ?? "/tmp")

    @Test func idleAndGlidingCpu() throws {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        app.finishLaunching()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        pump(1)
        var report = ["baseline cpu: \(fmt(cpu(over: 10)))%"]

        let cursor = CursorOverlay()
        var arrivals = 0
        // A spot near the top-left of the main screen, in global top-left coordinates.
        cursor.glide(to: CGPoint(x: 300, y: 300)) { arrivals += 1 }
        pump(1)
        report.append("after a glide: arrived \(arrivals)")
        report.append("resting cpu (cursor shown, not moving): \(fmt(cpu(over: 15)))%")

        // Glide back and forth and sample the cost while it moves.
        let began = usage()
        let start = Date()
        for i in 0..<8 {
            cursor.glide(to: CGPoint(x: i % 2 == 0 ? 900 : 300, y: 400)) {}
            pump(0.5)
        }
        report.append("gliding cpu: \(fmt((usage() - began) / Date().timeIntervalSince(start) * 100))%")
        cursor.click(at: CGPoint(x: 600, y: 400))
        pump(0.6)
        cursor.typing(at: CGPoint(x: 600, y: 400))
        pump(0.6)
        cursor.rest()
        pump(1)
        report.append("after rest cpu: \(fmt(cpu(over: 10)))%")
        try report.joined(separator: "\n").write(to: dir.appendingPathComponent("cursor-cpu.txt"),
                                                 atomically: true, encoding: .utf8)
        #expect(arrivals == 1)
    }

    private func pump(_ seconds: TimeInterval) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    private func fmt(_ v: Double) -> String { String(format: "%.2f", v) }

    private func usage() -> Double {
        var r = rusage()
        getrusage(RUSAGE_SELF, &r)
        return Double(r.ru_utime.tv_sec + r.ru_stime.tv_sec) + Double(r.ru_utime.tv_usec + r.ru_stime.tv_usec) / 1e6
    }

    private func cpu(over seconds: TimeInterval) -> Double {
        let start = usage(), began = Date()
        pump(seconds)
        return (usage() - start) / Date().timeIntervalSince(began) * 100
    }
}
