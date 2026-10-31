import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders Undo offscreen into PNGs (ADR 0024): under the bubble that says what a task did, on the task's card in the
/// conversation (ready, being undone, undone), on its page, and on Today's "Done today".
/// `MILO_RENDER_DIR=/tmp/milo-undo swift test --filter UndoRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct UndoRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")
    static let said = "Done: every cell of Book2 is red now, fill and font. I didn't save it."

    @Test func renderUndoEverywhere() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        TodayView.entrance = false
        let clock = ConversationsSidebar.now
        ConversationsSidebar.now = { Day.now }
        defer { TodayView.entrance = true; ConversationsSidebar.now = clock }

        for dark in [false, true] {
            let mode = dark ? "dark" : "light"
            try renderBubble(name: "undo-bubble-\(mode)", dark: dark)
            for state in [UndoPoint.State.ready, .undoing, .undone] {
                try renderWindow(.conversation("c-photos"), state: state, name: "undo-card-\(state)-\(mode)", dark: dark)
            }
            try renderWindow(.task("t-photos"), state: .ready, name: "undo-task-page-\(mode)", dark: dark)
            try renderWindow(.today, state: .ready, name: "undo-today-\(mode)", dark: dark)
        }
        try renderWindow(.conversation("c-photos"), state: .ready, name: "undo-card-narrow", dark: false,
                         size: CGSize(width: 440, height: 580))
    }

    private func renderBubble(name: String, dark: Bool) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.connected = true
        model.apply(.undoPoints([UndoPoint(id: "t1", title: "Excel red", said: Self.said)]))
        model.show(Self.said)
        let view = ZStack {
            Wallpaper(dark: dark)
            OverlayView(model: model)
        }
        .frame(width: OverlayPanel.size.width, height: OverlayPanel.size.height)
        try render(view, size: OverlayPanel.size, name: name, dark: dark)
    }

    private func renderWindow(_ page: WindowPage, state: UndoPoint.State, name: String, dark: Bool,
                              size: CGSize = CGSize(width: 780, height: 580)) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.connected = true
        model.apply(.undoPoints([UndoPoint(id: "t-photos", title: "Rename Friday's photos", state: state,
                                           said: "I renamed all 40 photos.")]))
        let route = WindowRoute(page: .live)
        route.go(page)
        let view = ConversationView(transcript: Day.transcript(), model: model,
                                    settings: ConversationSettings(talkKey: "right ⌥"), route: route,
                                    actions: WindowActions(reveal: { _ in }))
            .themed(by: model)
        try render(view, size: size, name: name, dark: dark, titled: true)
    }

    private func render(_ view: some View, size: CGSize, name: String, dark: Bool, titled: Bool = false) throws {
        let host = NSHostingView(rootView: view.frame(width: size.width, height: size.height))
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: titled ? [.titled] : [.borderless], backing: .buffered,
                              defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.6))
        host.layoutSubtreeIfNeeded()
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
