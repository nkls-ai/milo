import Combine
import Foundation

/// The setup window's checklist: one row per permission with a plain reason, checked live while the window is
/// open, and a last step to try dictation.
public final class SetupModel: ObservableObject {
    public struct Row: Identifiable, Equatable, Sendable {
        public let permission: Permission
        public let title: String
        public let reason: String
        /// Milo works without it; only some requests need it.
        public let optional: Bool
        public var state: PermissionState

        public var id: Permission { permission }
    }

    @Published public private(set) var rows: [Row]
    /// The key named in "Try it: hold … and say something".
    @Published public var dictateKey: String
    /// The user held a key and Milo listened since the window opened.
    @Published public private(set) var tried = false

    private let permissions: PermissionSource
    private let scheduler: Scheduler
    private var poll: ScheduledTask?

    public init(permissions: PermissionSource, scheduler: Scheduler, dictateKey: String = "fn") {
        self.permissions = permissions
        self.scheduler = scheduler
        self.dictateKey = dictateKey
        rows = Self.checklist.map { Row(permission: $0.0, title: $0.1, reason: $0.2, optional: $0.3, state: .unknown) }
        refresh()
    }

    static let checklist: [(Permission, String, String, Bool)] = [
        (.microphone, "Microphone", "So Milo can hear you while you hold a key. He doesn't listen otherwise.", false),
        (.accessibility, "Accessibility", "So Milo notices when you hold a key, and can type what you say into any app.", false),
        (.screenRecording, "Screen Recording", "So Milo can look at a window when you ask him “What's this?”.", false),
        (.calendars, "Calendars", "So Milo can tell you what's coming up and add appointments when you ask.", true),
        (.reminders, "Reminders", "So Milo can read and add reminders when you ask.", true),
        (.automation, "Mail and Notes", "So Milo can read your mail and notes and write drafts when you ask. He never sends mail.", true),
    ]

    /// Something Milo needs to work is missing: open the setup window.
    public var needsAttention: Bool {
        rows.contains { !$0.optional && $0.state != .granted }
    }

    public func refresh() {
        for index in rows.indices {
            let state = permissions.state(of: rows[index].permission)
            if rows[index].state != state { rows[index].state = state }
        }
    }

    /// Check again every second while the window is open, so a switch flipped in System Settings shows at once.
    public func startWatching() {
        refresh()
        tried = false
        poll?.cancel()
        poll = scheduler.every(1) { [weak self] in self?.refresh() }
    }

    public func stopWatching() {
        poll?.cancel()
        poll = nil
    }

    /// The row's button: macOS's own question the first time, the right page of System Settings after that.
    public func fix(_ permission: Permission) {
        if permissions.state(of: permission) == .notAsked {
            permissions.prompt(permission)
        } else {
            permissions.openSettings(permission)
        }
    }

    /// Milo's state changed: listening while the window is open means the last step worked.
    public func noticed(_ state: MiloState) {
        if poll != nil, state == .listening || state == .dictating, !tried { tried = true }
    }
}
