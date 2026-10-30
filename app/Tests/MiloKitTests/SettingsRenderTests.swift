import AppKit
import Foundation
import SwiftUI
import Testing
@testable import MiloKit

/// Renders the Settings window offscreen into PNGs for a visual check:
/// `MILO_RENDER_DIR=/tmp/milo-render swift test --filter SettingsRender`.
@Suite(.enabled(if: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] != nil))
@MainActor
struct SettingsRenderTests {
    static let size = CGSize(width: 500, height: 720)
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    /// What the brain reports, as in brain/src/milo/settings.py.
    static let report = SettingsReport(settings: [
        Setting(section: "ui", key: "character", value: "dragon", options: ["pip", "classic", "dragon", "kit", "glow"],
                labels: ["Pip", "Robot", "Dragon", "Kit", "Glow"]),
        Setting(section: "chat", key: "updates", value: "bubble", options: ["quiet", "bubble", "chatty"],
                labels: ["Only the answer", "Short notes in his bubble", "Tells you each step"], live: false),
        Setting(section: "dictation", key: "stream", value: "preview", options: ["off", "preview", "type"],
                labels: ["When you let go", "Show the words as you speak", "Type as you speak"]),
        Setting(section: "ui", key: "dictate_key", value: "fn",
                options: ["fn", "right_option", "right_command", "right_control"],
                labels: ["fn", "Right Option", "Right Command", "Right Control"]),
        Setting(section: "ui", key: "talk_key", value: "right_option",
                options: ["fn", "right_option", "right_command", "right_control"],
                labels: ["fn", "Right Option", "Right Command", "Right Control"]),
        Setting(section: "ui", key: "whats_this_key", value: "ctrl+option+m",
                options: ["ctrl+option+m", "ctrl+option+w", "ctrl+shift+m", ""],
                labels: ["Control-Option-M", "Control-Option-W", "Control-Shift-M", "Off"]),
        Setting(section: "ui", key: "voice", value: true),
    ])

    @Test func renderTheWindow() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var waiting = Self.report
        waiting.restart = true
        var refused = Self.report
        refused.error = "The dictate key and the talk key need to be different keys."
        for (name, report) in [("settings", Self.report), ("settings-restart", waiting), ("settings-error", refused),
                               ("settings-starting", nil)] as [(String, SettingsReport?)] {
            for dark in [false, true] {
                try render(SettingsModel(report: report), name: "\(name)-\(dark ? "dark" : "light")", dark: dark)
            }
        }
    }

    @Test func renderTheSetupWindow() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let permissions = FakePermissions()
        permissions.states = [.microphone: .notAsked, .screenRecording: .denied, .reminders: .notAsked,
                              .automation: .unknown]
        let setup = SetupModel(permissions: permissions, scheduler: ManualScheduler())
        for dark in [false, true] {
            try render(SetupView(setup: setup, done: {}), size: CGSize(width: 520, height: 800),
                       name: "setup-\(dark ? "dark" : "light")", dark: dark)
        }
        permissions.states = [:]
        setup.startWatching()
        setup.noticed(.dictating)
        try render(SetupView(setup: setup, done: {}), size: CGSize(width: 520, height: 800), name: "setup-done-light",
                   dark: false)
    }

    private func render(_ settings: SettingsModel, name: String, dark: Bool) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        try render(SettingsView(settings: settings, model: model, restart: {}), size: Self.size, name: name, dark: dark)
    }

    private func render(_ content: some View, size: CGSize, name: String, dark: Bool) throws {
        let view = content.frame(width: size.width, height: size.height)
        let host = NSHostingView(rootView: view)
        host.frame = NSRect(origin: .zero, size: size)
        let window = NSWindow(contentRect: host.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.appearance = NSAppearance(named: dark ? .darkAqua : .aqua)
        window.contentView = host
        host.layoutSubtreeIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.4))
        let rep = try #require(host.bitmapImageRepForCachingDisplay(in: host.bounds))
        host.cacheDisplay(in: host.bounds, to: rep)
        let png = try #require(rep.representation(using: .png, properties: [:]))
        try png.write(to: dir.appendingPathComponent("\(name).png"))
    }
}
