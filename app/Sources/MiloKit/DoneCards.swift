import Combine
import CoreGraphics
import Foundation

/// One thing Milo did, shown as a card by him.
public struct DoneCard: Identifiable, Equatable, Sendable {
    public let id: Int
    public let action: ActionDone
    /// When it came, on the model's clock: a timer's ring runs from here to its end.
    public let since: Date
}

/// The cards that come out of Milo when he has done something small for the user (`action_done`): an event, a
/// to-do, a timer. Each stays `stay` seconds, longer while the pointer is on the cards, then tucks back into him.
/// A click opens the item, and Undo takes it back through the task's Undo (ADR 0026). At most `most` show; a new
/// one pushes out the oldest.
public final class DoneCards: ObservableObject {
    /// Newest last.
    @Published public private(set) var cards: [DoneCard] = []
    /// The pointer is on the cards: they fan out and none tucks away.
    @Published public private(set) var hovered = false

    /// Seconds a card stays.
    public static let stay: TimeInterval = 4
    /// Seconds a card that ran out while the pointer was on the cards stays after it leaves.
    public static let afterHover: TimeInterval = 1.5
    /// How many cards show at once.
    public static let most = 3
    /// How often the pointer is checked while cards show: a panel that isn't key doesn't always hear hovers.
    static let pointerCheck: TimeInterval = 0.2

    /// Opens the item where it lives: Calendar at the event, Reminders, Notes, the draft. Set by main.swift.
    public var onOpen: ((ActionDone) -> Void)?
    /// The icon of the app named, for a card about something Milo opened. Set by main.swift.
    public var icon: ((String) -> CGImage?)?
    /// Sends the Undo of the task `undo`. Set by MiloModel.
    var onUndo: ((String) -> Void)?
    /// Whether the pointer is on the cards now, from the panel; nil leaves it to the view's hover alone.
    public var pointing: (() -> Bool)?
    /// Where the cards are in the overlay panel, top-left origin, so the panel lets clicks there through to them.
    /// Set by the view as it lays them out; empty while none show.
    public var area: CGRect = .zero

    private let scheduler: Scheduler
    private let date: () -> Date
    private var next = 0
    private var ends: [Int: ScheduledTask] = [:]
    private var poll: ScheduledTask?

    public init(scheduler: Scheduler, date: @escaping () -> Date = Date.init) {
        self.scheduler = scheduler
        self.date = date
    }

    /// A new card, by Milo, for `stay` seconds.
    public func add(_ action: ActionDone) {
        next += 1
        let card = DoneCard(id: next, action: action, since: date())
        cards.append(card)
        while cards.count > Self.most { remove(cards[0].id) }
        end(card.id, after: Self.stay)
        if poll == nil, pointing != nil {
            poll = scheduler.every(Self.pointerCheck) { [weak self] in
                guard let self, let on = pointing?() else { return }
                hover(on)
            }
        }
    }

    /// The pointer came onto the cards or left them.
    public func hover(_ on: Bool) {
        guard on != hovered else { return }
        hovered = on
    }

    /// The user clicked the card: the item opens where it lives and the card goes.
    public func open(_ id: Int) {
        guard let card = cards.first(where: { $0.id == id }) else { return }
        onOpen?(card.action)
        remove(id)
    }

    /// The user clicked Undo on the card. It stays while the pointer is on it, showing how the undo goes.
    public func undo(_ id: Int) {
        guard let card = cards.first(where: { $0.id == id }), !card.action.undo.isEmpty else { return }
        onUndo?(card.action.undo)
    }

    /// Tucks the card away now.
    public func dismiss(_ id: Int) {
        remove(id)
    }

    private func end(_ id: Int, after seconds: TimeInterval) {
        ends[id]?.cancel()
        ends[id] = scheduler.after(seconds) { [weak self] in
            guard let self else { return }
            // Held while the pointer is on the cards; checked here too, in case no hover was heard.
            if hovered || pointing?() == true { return end(id, after: Self.afterHover) }
            remove(id)
        }
    }

    private func remove(_ id: Int) {
        ends.removeValue(forKey: id)?.cancel()
        cards.removeAll { $0.id == id }
        guard cards.isEmpty else { return }
        poll?.cancel()
        poll = nil
        area = .zero
        if hovered { hovered = false }
    }
}

/// The words on a card, apart from its title.
public enum DoneCardText {
    /// The line under the title: when it is, and the detail; or where it went when it has neither.
    public static func line(_ action: ActionDone, now: Date, calendar: Calendar = .current,
                            locale: Locale = .current) -> String {
        let time = action.when.map { when(for: action.kind, $0, now: now, calendar: calendar, locale: locale) }
        let parts = [time, action.detail.isEmpty ? nil : action.detail].compactMap { $0 }
        if !parts.isEmpty { return parts.joined(separator: ", ") }
        switch action.kind {
        case .event: return action.app.isEmpty ? "In your calendar" : "In \(action.app)"
        case .todo: return action.app.isEmpty ? "On your list" : "In \(action.app)"
        case .reminder: return "I'll remind you"
        case .note: return action.app.isEmpty ? "In your notes" : "In \(action.app)"
        case .timer: return "Timer running"
        case .draft: return "Draft, not sent"
        case .shortcut: return "Shortcut ran"
        case .music: return "Playing"
        case .opened: return action.app.isEmpty ? "Opened" : "In \(action.app)"
        case .other: return "Done"
        }
    }

    /// "Today 15:00", "Tomorrow 09:00", "Thu 5 Nov, 15:00"; a timer says when it rings, and an event only its time,
    /// since its calendar page shows the day.
    static func when(for kind: ActionDone.Kind, _ date: Date, now: Date, calendar: Calendar, locale: Locale) -> String {
        var clock = Date.FormatStyle(date: .omitted, time: .shortened, locale: locale, calendar: calendar)
        clock.timeZone = calendar.timeZone
        let hour = date.formatted(clock)
        if kind == .timer { return "Rings at \(hour)" }
        if kind == .event { return hour }
        if calendar.isDate(date, inSameDayAs: now) { return "Today \(hour)" }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(date, inSameDayAs: tomorrow) {
            return "Tomorrow \(hour)"
        }
        var day = Date.FormatStyle(locale: locale, calendar: calendar).weekday(.abbreviated).day().month(.abbreviated)
        day.timeZone = calendar.timeZone
        return "\(date.formatted(day)), \(hour)"
    }

    /// What VoiceOver says for the card.
    public static func spoken(_ action: ActionDone, now: Date) -> String {
        let what: String = switch action.kind {
        case .event: "Added to your calendar"
        case .todo: "Added to your to-dos"
        case .reminder: "Reminder set"
        case .note: "Note written"
        case .timer: "Timer set"
        case .draft: "Draft written"
        case .shortcut: "Shortcut ran"
        case .music: "Playing"
        case .opened: "Opened"
        case .other: "Done"
        }
        var said = "\(what): \(action.title), \(line(action, now: now))"
        if action.kind == .event, let when = action.when {
            said += ", \(when.formatted(.dateTime.weekday(.wide).day().month(.wide)))"
        }
        return said
    }

    /// What a click on the card does, for VoiceOver and the tooltip.
    public static func opens(_ action: ActionDone) -> String {
        switch action.kind {
        case .reminder where action.app.isEmpty: "Shows your reminders in the Milo window"
        case .opened: "Shows it"
        default: action.app.isEmpty ? "Opens it" : "Opens it in \(action.app)"
        }
    }
}

/// Where a click on a card takes the user. Pure, so the choice is tested; `MacItemOpener` carries it out.
public enum DonePlace: Equatable, Sendable {
    /// Milo's own reminders: Today in the Milo window.
    case today
    /// The event in the calendar app, found by title near its start.
    case event(app: String, title: String, start: Date?)
    /// The to-do or reminder in the reminders app, found by title.
    case reminder(app: String, title: String)
    /// A page Milo opened.
    case page(String)
    /// The app it lives in.
    case app(String)
    /// Nowhere to go.
    case none

    public static func of(_ action: ActionDone) -> DonePlace {
        switch action.kind {
        case .reminder where action.app.isEmpty: return .today
        case .event: return .event(app: action.app.isEmpty ? "Calendar" : action.app, title: action.title,
                                   start: action.when)
        case .todo, .reminder: return .reminder(app: action.app.isEmpty ? "Reminders" : action.app, title: action.title)
        case .opened:
            if let page = page(action.detail) ?? page(action.title) { return .page(page) }
            return action.app.isEmpty ? .none : .app(action.app)
        default:
            let app = action.app.isEmpty ? defaultApp[action.kind] ?? "" : action.app
            return app.isEmpty ? .none : .app(app)
        }
    }

    /// The app a kind lives in when the brain names none.
    static let defaultApp: [ActionDone.Kind: String] = [
        .note: "Notes", .draft: "Mail", .shortcut: "Shortcuts", .music: "Music", .timer: "Clock",
    ]

    /// "https://youtube.com/…" as it is, "youtube.com" as https; anything else nil.
    static func page(_ text: String) -> String? {
        let text = text.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !text.contains(" ") else { return nil }
        if text.hasPrefix("https://") || text.hasPrefix("http://") { return text }
        let host = text.split(separator: "/").first.map(String.init) ?? ""
        guard host.contains("."), host.split(separator: ".").last.map({ $0.count >= 2 && $0.allSatisfy(\.isLetter) }) == true
        else { return nil }
        return "https://\(text)"
    }
}
