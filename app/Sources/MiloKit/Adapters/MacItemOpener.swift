import AppKit
import EventKit
import Foundation

/// Opens what a done card shows where it lives on the Mac (`DonePlace`): the event in Calendar, the to-do in
/// Reminders, the note in Notes, the page in the browser. It never asks macOS for access on a click: without
/// Calendar or Reminders access it opens the app itself. Also gives cards the icons of apps.
public final class MacItemOpener {
    private lazy var store = EKEventStore()
    private var icons: [String: CGImage] = [:]
    /// Shows Today in the Milo window, for Milo's own reminders.
    private let showToday: () -> Void
    /// Shows the conversation going on in the Milo window, where text Milo wrote waits to be copied.
    private let showConversation: () -> Void

    public init(showToday: @escaping () -> Void, showConversation: @escaping () -> Void = {}) {
        self.showToday = showToday
        self.showConversation = showConversation
    }

    public func open(_ action: ActionDone) {
        switch DonePlace.of(action) {
        case .today: showToday()
        case .conversation: showConversation()
        case let .event(app, title, start): openEvent(app: app, title: title, start: start)
        case let .reminder(app, title): openReminder(app: app, title: title)
        case let .page(page): if let url = URL(string: page) { NSWorkspace.shared.open(url) }
        case let .app(name): openApp(name)
        case .none: break
        }
    }

    /// The icon of the app called `name`, at 64 px, or nil when there is no such app.
    public func icon(_ name: String) -> CGImage? {
        if let icon = icons[name] { return icon }
        guard let url = Self.appURL(name) else { return nil }
        let image = NSWorkspace.shared.icon(forFile: url.path)
        var rect = CGRect(x: 0, y: 0, width: 64, height: 64)
        guard let icon = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { return nil }
        icons[name] = icon
        return icon
    }

    // MARK: Where

    /// Calendar shows the event itself through its `ical://ekevent/` link when Milo may read the calendar and finds
    /// it; otherwise Calendar opens as it is.
    private func openEvent(app: String, title: String, start: Date?) {
        guard app == "Calendar", let start, Self.allowed(.event) else { return openApp(app) }
        let window = store.predicateForEvents(withStart: start.addingTimeInterval(-60), end: start.addingTimeInterval(60),
                                              calendars: nil)
        let found = store.events(matching: window).first { $0.title == title } ?? store.events(matching: window).first
        guard let id = found?.calendarItemIdentifier,
              let url = URL(string: "ical://ekevent/\(id)?method=show&options=more") else { return openApp(app) }
        if !NSWorkspace.shared.open(url) { openApp(app) }
    }

    /// Reminders shows the reminder through its `x-apple-reminderkit://` link when Milo may read reminders and
    /// finds it; otherwise Reminders opens as it is.
    private func openReminder(app: String, title: String) {
        guard app == "Reminders", Self.allowed(.reminder) else { return openApp(app) }
        let predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: nil)
        store.fetchReminders(matching: predicate) { [weak self] reminders in
            let id = reminders?.last { $0.title == title }?.calendarItemIdentifier
            DispatchQueue.main.async {
                guard let id, let url = URL(string: "x-apple-reminderkit://REMCDReminder/\(id)"),
                      NSWorkspace.shared.open(url) else { return self?.openApp(app) ?? () }
            }
        }
    }

    private func openApp(_ name: String) {
        guard let url = Self.appURL(name) else { return }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        NSWorkspace.shared.openApplication(at: url, configuration: configuration)
    }

    private static func allowed(_ type: EKEntityType) -> Bool {
        let status = EKEventStore.authorizationStatus(for: type)
        return status == .fullAccess || status == .authorized
    }

    /// Apple's own apps by bundle id, anything else by name in the usual folders.
    static let bundles = [
        "Calendar": "com.apple.iCal", "Reminders": "com.apple.reminders", "Notes": "com.apple.Notes",
        "Mail": "com.apple.mail", "Music": "com.apple.Music", "Shortcuts": "com.apple.shortcuts",
        "Clock": "com.apple.clock", "Safari": "com.apple.Safari",
    ]

    static func appURL(_ name: String) -> URL? {
        if let bundle = bundles[name], let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundle) {
            return url
        }
        let folders = ["/Applications", "/System/Applications", "/System/Applications/Utilities",
                       NSHomeDirectory() + "/Applications"]
        return folders.map { URL(fileURLWithPath: $0).appendingPathComponent("\(name).app") }
            .first { FileManager.default.fileExists(atPath: $0.path) }
    }
}
