import Combine
import Foundation

/// The setup window's checklist: one row per permission with a plain reason, checked live while the window is
/// open, and a last step to try dictation.
///
/// Granting is made hard to get wrong: Milo is put in the permission's list before System Settings opens, a
/// small panel offers him as a tile to drag into the list, a "Fix it" clears a stale entry that shows as on but
/// doesn't count, and Screen Recording says when macOS wants Milo restarted.
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
    /// The window is open and checking. Scenes only animate while it is.
    @Published public private(set) var watching = false
    /// Show the panel with Milo's tile to drag into this permission's list in System Settings.
    @Published public private(set) var helper: Permission?
    /// System Settings was opened for these and they still aren't on: offer "Fix it" and say why.
    @Published public private(set) var stuck: Set<Permission> = []
    /// Screen Recording was opened in System Settings: macOS only counts it after Milo restarts.
    @Published public private(set) var restartForScreen = false

    /// Relaunches Milo. Set by the window.
    public var restart: (() -> Void)?

    private let permissions: PermissionSource
    private let scheduler: Scheduler
    private let defaults: UserDefaults
    private var poll: ScheduledTask?
    private var waits: [Permission: ScheduledTask] = [:]

    /// How long after opening System Settings an unchanged permission counts as stuck.
    static let patience: TimeInterval = 8
    static let grantedKey = "MiloPermissionsSeenGranted"

    public init(permissions: PermissionSource, scheduler: Scheduler, dictateKey: String = "fn",
                defaults: UserDefaults = .standard) {
        self.permissions = permissions
        self.scheduler = scheduler
        self.dictateKey = dictateKey
        self.defaults = defaults
        rows = Self.checklist.map { Row(permission: $0.0, title: $0.1, reason: $0.2, optional: $0.3, state: .unknown) }
        refresh()
    }

    static let checklist: [(Permission, String, String, Bool)] = [
        (.microphone, "Microphone", "Milo hears you while you hold a key, and turns what you say into words.", false),
        (.accessibility, "Accessibility", "Milo notices the key you hold, and types your words into any app.", false),
        (.screenRecording, "Screen Recording", "Milo looks at a window when you ask him “What's this?”.", false),
        (.calendars, "Calendars", "Milo tells you what's coming up and puts appointments in your calendar.", true),
        (.reminders, "Reminders", "Milo reads your reminders and adds new ones when you ask.", true),
        (.automation, "Mail and Notes", "Milo reads your mail and notes and writes drafts. He never sends anything.", true),
    ]

    /// Permissions whose System Settings list takes an app dragged in.
    static let draggable: Set<Permission> = [.accessibility, .screenRecording]
    /// Permissions with an entry that can go stale after Milo is rebuilt, which "Fix it" resets.
    static let resettable: Set<Permission> = [.accessibility, .screenRecording]

    /// Something Milo needs to work is missing: open the setup window.
    public var needsAttention: Bool {
        rows.contains { !$0.optional && $0.state != .granted }
    }

    public func state(of permission: Permission) -> PermissionState {
        rows.first { $0.permission == permission }?.state ?? .unknown
    }

    public func refresh() {
        var seen = seenGranted
        for index in rows.indices {
            let permission = rows[index].permission
            let state = permissions.state(of: permission)
            if rows[index].state != state { rows[index].state = state }
            if state == .granted {
                seen.insert(permission)
                settled(permission)
            } else if seen.contains(permission), Self.resettable.contains(permission) {
                // On before, off now without the user turning it off: usually a stale entry after a rebuild.
                if !stuck.contains(permission) { stuck.insert(permission) }
            }
        }
        if seen != seenGranted { seenGranted = seen }
    }

    /// Check again every second while the window is open, so a switch flipped in System Settings shows at once.
    public func startWatching() {
        tried = false
        watching = true
        refresh()
        poll?.cancel()
        poll = scheduler.every(1) { [weak self] in self?.refresh() }
    }

    public func stopWatching() {
        poll?.cancel()
        poll = nil
        watching = false
        helper = nil
        waits.values.forEach { $0.cancel() }
        waits = [:]
    }

    /// The row's button. The first time macOS's own question where there is one; otherwise Milo is put in the
    /// list first, so he is there to switch on, then the right page of System Settings opens.
    public func fix(_ permission: Permission) {
        let state = permissions.state(of: permission)
        permissions.register(permission)
        if state == .notAsked, Self.asksInADialog.contains(permission) { return }
        openSettings(permission)
    }

    /// "Fix it": forget Milo's stale entry, add him again and open the page, so the switch counts this time.
    public func repair(_ permission: Permission) {
        guard Self.resettable.contains(permission) else { return }
        permissions.reset(permission)
        seenGranted.remove(permission)
        stuck.remove(permission)
        permissions.register(permission)
        openSettings(permission)
    }

    public func closeHelper() {
        helper = nil
    }

    /// Milo's state changed: listening while the window is open means the last step worked.
    public func noticed(_ state: MiloState) {
        if watching, state == .listening || state == .dictating, !tried { tried = true }
    }

    /// Where macOS shows a dialog on `register` while it hasn't been asked.
    static let asksInADialog: Set<Permission> = [.microphone, .calendars, .reminders, .automation]

    private func openSettings(_ permission: Permission) {
        permissions.openSettings(permission)
        if Self.draggable.contains(permission) { helper = permission }
        if permission == .screenRecording { restartForScreen = true }
        waits[permission]?.cancel()
        waits[permission] = scheduler.after(Self.patience) { [weak self] in
            guard let self, state(of: permission) != .granted, Self.resettable.contains(permission) else { return }
            stuck.insert(permission)
        }
    }

    private func settled(_ permission: Permission) {
        if stuck.contains(permission) { stuck.remove(permission) }
        if helper == permission { helper = nil }
        if permission == .screenRecording, restartForScreen { restartForScreen = false }
        waits.removeValue(forKey: permission)?.cancel()
    }

    private var seenGranted: Set<Permission> {
        get { Set((defaults.stringArray(forKey: Self.grantedKey) ?? []).compactMap(Permission.init(rawValue:))) }
        set { defaults.set(newValue.map(\.rawValue).sorted(), forKey: Self.grantedKey) }
    }
}
