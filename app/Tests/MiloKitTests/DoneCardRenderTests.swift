import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the done cards by Milo and the caption under the working outline offscreen into PNGs.
/// `MILO_RENDER_DIR=/tmp/milo-done swift test --filter DoneCardRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct DoneCardRenderTests {
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    static func tomorrow(_ hour: Int, _ minute: Int = 0) -> Date {
        let calendar = Calendar.current
        let day = calendar.date(byAdding: .day, value: 1, to: calendar.startOfDay(for: Date()))!
        return calendar.date(bySettingHour: hour, minute: minute, second: 0, of: day)!
    }

    static let every: [ActionDone] = [
        ActionDone(kind: .event, title: "Dentist", detail: "Dr. Lee", when: tomorrow(15), app: "Calendar", undo: "t1"),
        ActionDone(kind: .todo, title: "Buy oat milk", app: "Reminders", undo: "t2"),
        ActionDone(kind: .timer, title: "Pasta", when: Date().addingTimeInterval(9 * 60 + 20)),
        ActionDone(kind: .note, title: "Packing list", detail: "Passport, charger, socks", app: "Notes"),
        ActionDone(kind: .draft, title: "Lunch on Friday?", detail: "To Anna", app: "Mail", undo: "t3"),
        ActionDone(kind: .reminder, title: "Call the dentist", when: tomorrow(9)),
        ActionDone(kind: .shortcut, title: "Text Anna I'm late"),
        ActionDone(kind: .music, title: "Lofi beats", detail: "Spotify playlist"),
        ActionDone(kind: .opened, title: "YouTube", detail: "youtube.com", app: "Safari"),
    ]

    @Test func renderTheCards() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for dark in [false, true] {
            let tag = dark ? "dark" : "light"
            try renderCorner([Self.every[0]], name: "done-one-\(tag)", dark: dark)
            try renderCorner(Array(Self.every[0...2]), name: "done-deck-\(tag)", dark: dark)
            try renderCorner(Array(Self.every[0...2]), name: "done-fanned-\(tag)", dark: dark, hovered: true)
            try renderEvery(name: "done-every-\(tag)", dark: dark)
            try renderOutline(name: "outline-caption-\(tag)", dark: dark)
        }
        try renderCorner([Self.every[1]], name: "done-with-bubble", dark: false,
                         bubble: "Done, oat milk is on your list.")
    }

    private func renderCorner(_ actions: [ActionDone], name: String, dark: Bool, hovered: Bool = false,
                              bubble: String? = nil) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        model.connected = true
        if let bubble { model.show(bubble) }
        actions.forEach { model.done.add($0) }
        if hovered { model.done.hover(true) }
        let view = ZStack {
            Wallpaper(dark: dark)
            OverlayView(model: model)
        }
        try render(view, size: OverlayPanel.size, name: name, dark: dark)
    }

    /// Every kind of card, still, in a column.
    private func renderEvery(name: String, dark: Bool) throws {
        let done = DoneCards(scheduler: ManualScheduler())
        let theme = Theme.for(.milo)
        let view = ZStack {
            Wallpaper(dark: dark)
            VStack(spacing: 14) {
                ForEach(Array(Self.every.enumerated()), id: \.offset) { index, action in
                    DoneCardView(card: DoneCard(id: index, action: action, since: Date()),
                                 point: action.undo.isEmpty ? nil : UndoPoint(id: action.undo, title: action.title),
                                 done: done, now: Date())
                }
            }
            .environment(\.miloTheme, theme)
        }
        try render(view, size: CGSize(width: 220, height: CGFloat(Self.every.count) * 70 + 20), name: name, dark: dark)
    }

    /// A window Milo works in, with its outline and the step under it.
    private func renderOutline(name: String, dark: Bool) throws {
        let view = ZStack {
            Wallpaper(dark: dark)
            RoundedRectangle(cornerRadius: 10).fill(dark ? Color(white: 0.16) : .white)
                .padding(EdgeInsets(top: 6, leading: 6, bottom: 6 + WorkingOutlineView.captionRoom, trailing: 6))
            WorkingOutlineView(caption: "Typing “youtube.com” in Safari")
        }
        try render(view, size: CGSize(width: 520, height: 320), name: name, dark: dark)
    }

    private func render(_ view: some View, size: CGSize, name: String, dark: Bool) throws {
        let host = NSHostingView(rootView: view.frame(width: size.width, height: size.height))
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.borderless], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(1.2))  // landed, and the check drawn in
        host.layoutSubtreeIfNeeded()
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
