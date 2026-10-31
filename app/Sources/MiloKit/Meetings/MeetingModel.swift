import Combine
import Foundation

/// What the app shows of meeting notes: the status the capsule by Milo, the menu bar and the meeting's page follow,
/// each meeting's lines as they are transcribed, and finished notes. Built from `meeting_status`, `meeting_lines` and
/// `meeting_notes`; the buttons go back through the closures MiloController sets. Updated on the main queue.
/// See docs/design/meetings.md.
public final class MeetingModel: ObservableObject {
    @Published public private(set) var status = MeetingStatus()
    /// Lines by meeting id, in time order.
    @Published public private(set) var lines: [String: [MeetingLine]] = [:]
    /// Finished notes by meeting id.
    @Published public private(set) var notes: [String: MeetingNotes] = [:]
    /// The consent line was copied a moment ago: the button says so.
    @Published public private(set) var copied = false
    /// The meeting whose notes were copied a moment ago.
    @Published public private(set) var copiedNotes: String?

    /// Stop now: the recorder stops at once, the brain hears after. Set by the controller.
    public var onStop: (() -> Void)?
    /// Pause (true) or go on. Set by the controller.
    public var onPause: ((Bool) -> Void)?
    /// Show meeting `id` in the Milo window. Set by main.swift.
    public var onOpen: ((String) -> Void)?
    /// Commands that need no more than the brain. Set by the controller.
    public var send: ((BrainCommand) -> Void)?
    /// Puts text on the clipboard. Set by main.swift; tests read what was copied.
    public var copy: ((String) -> Void)?

    /// Seconds on a monotonic clock.
    let now: () -> TimeInterval
    private var statusAt: TimeInterval = 0

    public init(clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        now = clock
    }

    /// How long the meeting has gone on: counting while it records, still once it stopped.
    public func elapsed(at time: TimeInterval? = nil) -> TimeInterval {
        guard status.live else { return status.elapsed }
        return status.elapsed + max(0, (time ?? now()) - statusAt)
    }

    /// "0:04", "12:34", or "1:02:05" past an hour.
    public static func clock(_ seconds: TimeInterval) -> String {
        let s = max(0, Int(seconds))
        let (h, m, rest) = (s / 3600, s / 60 % 60, s % 60)
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, rest) : String(format: "%d:%02d", m, rest)
    }

    /// "32 min", "1 h 05 min", or "under a minute".
    public static func length(_ seconds: TimeInterval) -> String {
        let minutes = Int((seconds / 60).rounded())
        if minutes < 1 { return "under a minute" }
        if minutes < 60 { return "\(minutes) min" }
        return String(format: "%d h %02d min", minutes / 60, minutes % 60)
    }

    public func apply(_ event: BrainEvent) {
        switch event {
        case let .meetingStatus(new):
            statusAt = now()
            if new != status { status = new }
        case let .meetingLines(id, list, reset):
            var held = reset ? [] : lines[id] ?? []
            for line in list {
                if let i = held.firstIndex(where: { $0.id == line.id }) { held[i] = line } else { held.append(line) }
            }
            held.sort { $0.at < $1.at }
            lines[id] = held
        case let .meetingNotes(page):
            notes[page.id] = page
        default:
            break
        }
    }

    /// The meeting `id` going on now, or being written.
    public func isCurrent(_ id: String) -> Bool {
        !id.isEmpty && status.id == id && status.phase != .none && status.phase != .done
    }

    // MARK: Buttons

    public func stop() { onStop?() }

    public func pause(_ on: Bool) { onPause?(on) }

    /// Show the meeting in the window.
    public func open(_ id: String) {
        guard !id.isEmpty else { return }
        onOpen?(id)
    }

    /// The page for meeting `id` appeared: ask for what it shows.
    public func request(_ id: String) {
        guard !id.isEmpty else { return }
        send?(.openMeeting(id: id))
    }

    /// "Add to Reminders" on to-do `index`; nil for all of the user's own. Marked at once, the brain confirms it.
    public func addTodo(_ id: String, _ index: Int? = nil) {
        guard var page = notes[id] else { return }
        for i in page.todos.indices where index.map({ $0 == i }) ?? page.todos[i].mine {
            page.todos[i].added = true
        }
        notes[id] = page
        send?(.meetingTodo(id: id, index: index ?? -1))
    }

    public func draftMail(_ id: String) {
        guard var page = notes[id], !page.mailDrafted else { return }
        page.mailDrafted = true
        notes[id] = page
        send?(.meetingMail(id: id))
    }

    /// "Copy a note for the chat": the line Milo suggests, on the clipboard.
    public func copyConsent() {
        let line = status.consent.isEmpty ? Self.consent : status.consent
        copy?(line)
        copied = true
    }

    /// "Copy notes": notes.md as it is, ready to paste anywhere.
    public func copyNotes(_ id: String) {
        guard let page = notes[id] else { return }
        copy?(page.markdown)
        copiedNotes = id
    }

    /// The line for the call's chat when the brain didn't send one.
    public static let consent = "Milo is taking notes for me. They stay on my computer."
}

/// Whether the transcript follows new lines: it does until the user scrolls up, and again once they come back to
/// the end or press "Back to now". Counts what arrived meanwhile.
public struct TranscriptFollow: Equatable, Sendable {
    public private(set) var following = true
    /// Lines that arrived while the user read further up.
    public private(set) var unseen = 0

    public init() {}

    /// How close to the end still counts as at the end, in points.
    public static let slack: CGFloat = 40

    /// The list scrolled: `distance` is how far its end is below the visible part.
    public mutating func scrolled(distanceToEnd distance: CGFloat) {
        let atEnd = distance <= Self.slack
        if atEnd != following { following = atEnd }
        if atEnd { unseen = 0 }
    }

    /// New lines came in. True: scroll to the end.
    public mutating func arrived(_ count: Int) -> Bool {
        guard count > 0 else { return false }
        if following { return true }
        unseen += count
        return false
    }

    /// "Back to now".
    public mutating func jump() {
        following = true
        unseen = 0
    }
}
