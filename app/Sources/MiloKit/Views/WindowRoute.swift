import AppKit
import Foundation
import SwiftUI

/// Where the Milo window is. See docs/design/conversations.md.
public enum WindowPage: Hashable, Sendable {
    /// Home: what Milo does now, what waits for you, reminders, what got done.
    case today
    /// The conversation going on, whichever it is: it follows a split.
    case live
    /// One conversation, kept even when another starts.
    case conversation(String)
    /// A task's own page.
    case task(String)

    /// How deep it sits, so a move goes left or right: Today, then conversations, then tasks.
    var depth: Int {
        switch self {
        case .today: 0
        case .live, .conversation: 1
        case .task: 2
        }
    }
}

/// The window's navigation: the page, the way back, the sidebar, the search field.
public final class WindowRoute: ObservableObject {
    @Published public private(set) var page: WindowPage
    @Published public private(set) var back: [WindowPage] = []
    /// The last move went deeper (true) or back up (false), for the side a page slides in from.
    @Published public private(set) var forward = true
    @Published public var search = ""
    /// The sidebar shown in a narrow window, where it folds away by default.
    @Published public var sidebarShown = false

    public init(page: WindowPage = .today) {
        self.page = page
    }

    public func go(_ page: WindowPage) {
        guard page != self.page else { return }
        forward = page.depth >= self.page.depth
        back.append(self.page)
        if back.count > 20 { back.removeFirst() }
        self.page = page
    }

    public func goBack() {
        guard let previous = back.popLast() else {
            if page != .today { forward = false; page = .today }
            return
        }
        forward = false
        page = previous
    }

    /// The conversation a page shows, given the current one.
    public func conversation(current: String) -> String? {
        switch page {
        case .live: current.isEmpty ? nil : current
        case let .conversation(id): id
        default: nil
        }
    }
}

/// What the window asks of the brain besides the model's own buttons. MiloController makes the real one.
public struct WindowActions {
    public var open: (String) -> Void
    public var search: (String) -> Void
    public var rename: (String, String) -> Void
    public var newConversation: () -> Void
    public var older: (String) -> Void
    public var send: (_ text: String, _ speak: Bool, _ conversation: String) -> Void
    /// Show a file in the Finder.
    public var reveal: (String) -> Void

    public init(open: @escaping (String) -> Void = { _ in }, search: @escaping (String) -> Void = { _ in },
                rename: @escaping (String, String) -> Void = { _, _ in }, newConversation: @escaping () -> Void = {},
                older: @escaping (String) -> Void = { _ in },
                send: @escaping (String, Bool, String) -> Void = { _, _, _ in },
                reveal: @escaping (String) -> Void = WindowActions.showInFinder) {
        self.open = open
        self.search = search
        self.rename = rename
        self.newConversation = newConversation
        self.older = older
        self.send = send
        self.reveal = reveal
    }

    public static func showInFinder(_ path: String) {
        let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
}

/// The list's day groups: Today, Yesterday, This week, then months, the latest first.
enum DayGroups {
    static func group(_ conversations: [ConversationInfo], now: Date = Date(),
                      calendar: Calendar = .current) -> [(title: String, items: [ConversationInfo])] {
        var groups: [(title: String, items: [ConversationInfo])] = []
        for conversation in conversations.sorted(by: { $0.last > $1.last }) {
            let title = heading(conversation.last, now: now, calendar: calendar)
            if groups.last?.title == title {
                groups[groups.count - 1].items.append(conversation)
            } else {
                groups.append((title, [conversation]))
            }
        }
        return groups
    }

    static func heading(_ date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        if calendar.isDate(date, inSameDayAs: now) { return "Today" }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now), calendar.isDate(date, inSameDayAs: yesterday) {
            return "Yesterday"
        }
        let startOfToday = calendar.startOfDay(for: now)
        if let weekAgo = calendar.date(byAdding: .day, value: -6, to: startOfToday), date >= weekAgo, date < now {
            return "This week"
        }
        let sameYear = calendar.component(.year, from: date) == calendar.component(.year, from: now)
        return date.formatted(sameYear ? .dateTime.month(.wide) : .dateTime.month(.wide).year())
    }

    /// The short time on a row: "9:12" today, "Tue" this week, "28 Oct" before.
    static func time(_ date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        switch heading(date, now: now, calendar: calendar) {
        case "Today": date.formatted(date: .omitted, time: .shortened)
        case "Yesterday": "Yesterday"
        case "This week": date.formatted(.dateTime.weekday(.abbreviated))
        default: date.formatted(.dateTime.day().month(.abbreviated))
        }
    }
}
