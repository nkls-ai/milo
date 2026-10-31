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
    // Tall enough for the approvals card with its allowed apps (ADR 22) and the Meeting notes card.
    static let size = CGSize(width: 520, height: 1760)
    let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MILO_RENDER_DIR"] ?? "/tmp")

    /// What the brain reports, as in brain/src/milo/settings.py.
    static let report = SettingsReport(settings: [
        Setting(section: "chat", key: "updates", value: "bubble", options: ["quiet", "bubble", "chatty"],
                labels: ["Only the answer", "Short notes in his bubble", "Tells you each step"], live: false),
        Setting(section: "dictation", key: "stream", value: "preview", options: ["off", "preview", "type"],
                labels: ["When you let go", "Show the words as you speak", "Type as you speak"]),
        Setting(section: "dictation", key: "learn", value: true),
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
        Setting(section: "ui", key: "hide_after_s", value: 60, options: [30, 60, 300, 0],
                labels: ["After 30 seconds", "After a minute", "After 5 minutes", "Never"]),
        Setting(section: "hands", key: "show_window", value: true),
        Setting(section: "approvals", key: "ask", value: "task", options: ["step", "task", "auto"],
                labels: ["Every step", "Once per task", "Only when it matters (auto)"], live: true),
        Setting(section: "approvals", key: "allowed_apps", value: .array([
            .object(["name": "Microsoft Excel", "bundle": ""]),
            .object(["name": "Numbers", "bundle": "com.apple.iWork.Numbers"]),
        ]), live: true),
        Setting(section: "meetings", key: "auto", value: "ask", options: ["ask", "calendar", "off"],
                labels: ["Ask me", "Without asking when my calendar has a meeting", "Never ask"]),
        Setting(section: "meetings", key: "always", value: "Zoom, Microsoft Teams"),
        Setting(section: "meetings", key: "never", value: "WhatsApp"),
    ])

    @Test func renderTheWindow() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var waiting = Self.report
        waiting.restart = true
        var refused = Self.report
        refused.error = "The dictate key and the talk key need to be different keys."
        for dark in [false, true] {
            try render(SettingsModel(report: Self.report), name: "settings-milo-\(dark ? "dark" : "light")", dark: dark)
        }
        try render(SettingsModel(report: waiting), name: "settings-restart-light", dark: false)
        var auto = Self.report
        auto.settings[auto.settings.count - 2].value = "auto"
        auto.settings[auto.settings.count - 1].value = .array([])
        try render(SettingsModel(report: auto), name: "settings-auto-light", dark: false)
        try render(SettingsModel(report: auto), name: "settings-auto-dark", dark: true)
        try render(SettingsModel(report: refused), name: "settings-error-light", dark: false)
        try render(SettingsModel(report: nil), name: "settings-starting-dark", dark: true)
    }

    @Test func renderTheSetupWindow() throws {
        _ = NSApplication.shared
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let size = CGSize(width: 560, height: 1500)
        let (setup, permissions) = Self.setup([.microphone: .notAsked, .screenRecording: .denied,
                                               .accessibility: .denied, .reminders: .notAsked, .automation: .unknown])
        setup.fix(.accessibility)  // the drag-in hint
        setup.fix(.screenRecording)  // the restart note
        permissions.states[.accessibility] = .granted
        setup.refresh()
        for dark in [false, true] {
            try render(SetupView(setup: setup, done: {}).environment(\.miloTheme, .milo), size: size,
                       name: "setup-milo-\(dark ? "dark" : "light")", dark: dark)
        }
        let scheduler = ManualScheduler()
        let (stuck, _) = Self.setup([.accessibility: .denied, .screenRecording: .denied], scheduler: scheduler)
        stuck.startWatching()
        stuck.fix(.accessibility)
        scheduler.advance(by: SetupModel.patience)
        try render(SetupView(setup: stuck, done: {}).environment(\.miloTheme, .milo), size: size,
                   name: "setup-stuck-light", dark: false)
        // The apps macOS was asked about (ADR 25), under the optional rows.
        let suite = "SettingsRender-apps-\(UUID().uuidString)"
        let apps = ControlledApps(defaults: UserDefaults(suiteName: suite)!)
        apps.note(AccessAnswer(.yes, app: AccessApp(name: "Microsoft Excel", bundle: "com.microsoft.Excel")))
        apps.note(AccessAnswer(.yes, app: AccessApp(name: "Mail", bundle: "com.apple.mail")))
        apps.note(AccessAnswer(.no, app: AccessApp(name: "Numbers", bundle: "com.apple.iWork.Numbers")))
        let (withApps, _) = Self.setup([.microphone: .granted, .accessibility: .granted, .screenRecording: .granted])
        for dark in [false, true] {
            try render(SetupView(setup: withApps, apps: apps, done: {}).environment(\.miloTheme, .milo),
                       size: size, name: "setup-apps-\(dark ? "dark" : "light")", dark: dark)
            try render(ControlledAppsCard(apps: apps, open: {}).padding(16).environment(\.miloTheme, .milo),
                       size: CGSize(width: 520, height: 260), name: "setup-apps-card-\(dark ? "dark" : "light")", dark: dark)
        }
        let (ready, _) = Self.setup([:])
        ready.startWatching()
        ready.noticed(.dictating)
        ready.stopWatching()
        try render(SetupView(setup: ready, done: {}).environment(\.miloTheme, .milo), size: size,
                   name: "setup-done-light", dark: false)
        for dark in [false, true] {
            try render(DragHelperView(appURL: URL(fileURLWithPath: "/Applications/Calculator.app"),
                                      icon: NSWorkspace.shared.icon(forFile: "/System/Applications/Calculator.app"),
                                      close: {}).environment(\.miloTheme, .milo),
                       size: CGSize(width: 210, height: 230), name: "drag-helper-\(dark ? "dark" : "light")", dark: dark)
        }
    }

    private static func setup(_ states: [Permission: PermissionState], scheduler: ManualScheduler = ManualScheduler())
        -> (SetupModel, FakePermissions) {
        let permissions = FakePermissions()
        permissions.states = states
        let name = "SettingsRender-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: name)!
        defaults.removePersistentDomain(forName: name)
        return (SetupModel(permissions: permissions, scheduler: scheduler, defaults: defaults), permissions)
    }

    private func render(_ settings: SettingsModel, name: String, dark: Bool) throws {
        let model = MiloModel(scheduler: ManualScheduler())
        try render(SettingsView(settings: settings, model: model, restart: {}, showWords: {}).themed(by: model),
                   size: Self.size,
                   name: name, dark: dark)
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
