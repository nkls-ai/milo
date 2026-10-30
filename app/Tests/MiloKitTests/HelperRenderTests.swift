import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the helpers offscreen into PNGs: small birds next to Milo, and the helpers list in the Milo window.
/// `MILO_RENDER_DIR=/tmp/milo-helpers swift test --filter HelperRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct HelperRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    static let three: [HelperInfo] = [
        HelperInfo(id: "t1", title: "Budget table in Excel", status: .working, step: "Typing “Monday” in Excel",
                   progress: 0.4),
        HelperInfo(id: "t2", title: "Flights to Lisbon", status: .needsYou, step: "Waiting for your answer"),
        HelperInfo(id: "t3", title: "Sort downloads", status: .queued, step: "Waiting for a free helper"),
    ]

    static let finishing: [HelperInfo] = [
        HelperInfo(id: "t1", title: "Budget table in Excel", status: .done, progress: 1),
        HelperInfo(id: "t2", title: "Flights", status: .failed),
        HelperInfo(id: "t3", title: "Sort downloads", status: .stopped, step: "Stopped"),
        HelperInfo(id: "t4", title: "Dentist email", status: .working, step: "Writing a draft to Dr. Lee"),
    ]

    @Test func renderTheBirdsAndTheList() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            let tag = dark ? "dark" : "light"
            try renderCorner(helpers: Self.three, character: .pip, name: "helpers-corner-\(tag)", dark: dark)
            try renderCorner(helpers: Self.finishing, character: .pip, name: "helpers-corner-finishing-\(tag)",
                             dark: dark)
            try renderWindow(helpers: Self.three, name: "helpers-window-\(tag)", dark: dark)
        }
        try renderCorner(helpers: Self.three, character: .classic, name: "helpers-corner-classic", dark: false)
        try renderCorner(helpers: [Self.three[0]], character: .pip, name: "helpers-corner-one", dark: false,
                         bubble: "Budget table in Excel: Opening Microsoft Excel")
    }

    private func renderCorner(helpers: [HelperInfo], character: CharacterStyle, name: String, dark: Bool,
                              bubble: String? = nil) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.connected = true
        model.character = character
        model.apply(.helpers(helpers))
        if let bubble { model.show(bubble) }
        let view = ZStack {
            PipRenderTests.Wallpaper(dark: dark)
            OverlayView(model: model)
        }
        .frame(width: OverlayPanel.size.width, height: OverlayPanel.size.height)
        try render(view, size: OverlayPanel.size, name: name, dark: dark)
    }

    private func renderWindow(helpers: [HelperInfo], name: String, dark: Bool) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.connected = true
        model.apply(.helpers(helpers))
        let entries = Samples.oneTurn + [
            TranscriptEntry(id: "t1", date: Samples.at(10), kind: .task, text: "Make a budget table in Excel for November",
                            status: .running, steps: [
                                ActivityStep(id: "1", kind: "app", title: "Opening Microsoft Excel", detail: "", status: .done),
                                ActivityStep(id: "2", kind: "app", title: "Typing “Monday” in Excel", detail: "",
                                             status: .running),
                            ]),
            TranscriptEntry(id: "t2", date: Samples.at(12), kind: .task, text: "Find flights to Lisbon in March",
                            status: .running, steps: [
                                ActivityStep(id: "1", kind: "web", title: "Searching the web for “Lisbon flights March”",
                                             detail: "", status: .done),
                            ]),
            TranscriptEntry(id: "t3", date: Samples.at(13), kind: .task, text: "Sort my downloads by type", status: .running),
        ]
        let view = ConversationView(transcript: TranscriptModel(entries: entries), model: model,
                                    settings: ConversationSettings(talkKey: "right ⌥"), send: { _, _ in })
        try render(view, size: CGSize(width: 420, height: 560), name: name, dark: dark)
    }

    private func render(_ view: some View, size: CGSize, name: String, dark: Bool) throws {
        let host = NSHostingView(rootView: view.frame(width: size.width, height: size.height))
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
