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
///
/// The title and the detail come from the brain, in the language Milo answered in. The card's own words follow that
/// language (`ActionDone.lang`), so a German line never sits above an English card; when the brain names none, they
/// follow the system's. English and German, like Milo's spoken lines; any other language gets English.
public enum DoneCardText {
    /// The line under the title: when it is, and the detail; or where it went when it has neither.
    public static func line(_ action: ActionDone, now: Date, calendar: Calendar = .current,
                            locale: Locale = .current) -> String {
        let (w, locale) = words(action, locale)
        let time = action.when.map { when(for: action.kind, $0, now: now, calendar: calendar, locale: locale, words: w) }
        let parts = [time, action.detail.isEmpty ? nil : action.detail].compactMap { $0 }
        if !parts.isEmpty { return parts.joined(separator: ", ") }
        let inApp = { (fallback: String) in action.app.isEmpty ? w(fallback) : w("In %@", action.app) }
        switch action.kind {
        case .event: return inApp("In your calendar")
        case .todo: return inApp("On your list")
        case .reminder: return w("I'll remind you")
        case .note: return inApp("In your notes")
        case .timer: return w("Timer running")
        case .alarm: return w("Alarm set")
        case .draft: return w("Draft, not sent")
        case .shortcut: return w("Shortcut ran")
        // The title says what happened ("Paused"); the player, if it said which one it is.
        case .music: return action.app.isEmpty ? w("Music") : action.app
        case .opened: return inApp("Opened")
        case .written: return inApp("Ready to copy")
        case .copied: return w("On your clipboard")
        case .message: return w("Sent")
        case .call: return w("Called")
        case .sound: return w("Sound")
        case .brightness: return w("Screen")
        case .other: return w("Done")
        }
    }

    /// "Today 15:00", "Tomorrow 09:00", "Thu 5 Nov, 15:00"; a timer says when it rings, and an event only its time,
    /// since its calendar page shows the day.
    static func when(for kind: ActionDone.Kind, _ date: Date, now: Date, calendar: Calendar, locale: Locale,
                     words w: Words = Words("en")) -> String {
        var clock = Date.FormatStyle(date: .omitted, time: .shortened, locale: locale, calendar: calendar)
        clock.timeZone = calendar.timeZone
        let hour = date.formatted(clock)
        if kind == .timer { return w("Rings at %@", hour) }
        if kind == .event { return hour }
        if calendar.isDate(date, inSameDayAs: now) { return "\(w("Today")) \(hour)" }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(date, inSameDayAs: tomorrow) {
            return "\(w("Tomorrow")) \(hour)"
        }
        var day = Date.FormatStyle(locale: locale, calendar: calendar).weekday(.abbreviated).day().month(.abbreviated)
        day.timeZone = calendar.timeZone
        return "\(date.formatted(day)), \(hour)"
    }

    /// What VoiceOver says for the card. An event, a to-do, a reminder or a timer can also have been deleted, ticked
    /// off or stopped, which the detail says ("Deleted"), so those name only what it is.
    public static func spoken(_ action: ActionDone, now: Date, locale: Locale = .current) -> String {
        let (w, dates) = words(action, locale)
        let what: String = switch action.kind {
        case .event: w("Calendar")
        case .todo: w("To-do")
        case .reminder: w("Reminder")
        case .note: w("Note written")
        case .timer: w("Timer")
        case .alarm: w("Alarm")
        case .draft: w("Draft written")
        case .shortcut: w("Shortcut ran")
        case .music: w("Music")
        case .opened: w("Opened")
        case .written: action.app.isEmpty ? w("Written, ready to copy") : w("Written")
        case .copied: w("Copied")
        case .message: w("Message sent")
        case .call: w("Call")
        case .sound: w("Sound")
        case .brightness: w("Screen")
        case .other: w("Done")
        }
        var said = "\(what): \(action.title), \(line(action, now: now, locale: locale))"
        if action.kind == .event, let when = action.when {
            said += ", \(when.formatted(Date.FormatStyle(locale: dates).weekday(.wide).day().month(.wide)))"
        }
        return said
    }

    /// What a click on the card does, for VoiceOver and the tooltip.
    public static func opens(_ action: ActionDone, locale: Locale = .current) -> String {
        let (w, _) = words(action, locale)
        switch action.kind {
        case .reminder where action.app.isEmpty: return w("Shows your reminders in the Milo window")
        case .opened: return w("Shows it")
        case .written where action.app.isEmpty, .copied: return w("Shows it in the Milo window, to copy")
        default: return action.app.isEmpty ? w("Opens it") : w("Opens it in %@", action.app)
        }
    }

    /// The words for this card, and the locale its dates are written in: the system's, unless Milo spoke another
    /// language the card has words in.
    static func words(_ action: ActionDone, _ locale: Locale) -> (Words, Locale) {
        let system = locale.language.languageCode?.identifier ?? "en"
        let wanted = Words(action.lang.isEmpty ? system : action.lang)
        return (wanted, action.lang.isEmpty || wanted.code == system ? locale : Locale(identifier: wanted.code))
    }

    /// A card's own words in one language, looked up by their English text; "%@" takes the one argument.
    struct Words {
        let code: String

        init(_ code: String) {
            self.code = code == "de" ? "de" : "en"
        }

        func callAsFunction(_ english: String, _ argument: String = "") -> String {
            let text = code == "de" ? Self.german[english] ?? english : english
            return text.replacingOccurrences(of: "%@", with: argument)
        }

        static let german: [String: String] = [
            "In your calendar": "In deinem Kalender", "In %@": "In %@", "On your list": "Auf deiner Liste",
            "I'll remind you": "Ich erinnere dich", "In your notes": "In deinen Notizen", "Timer running": "Timer läuft",
            "Draft, not sent": "Entwurf, nicht gesendet", "Shortcut ran": "Kurzbefehl ausgeführt", "Music": "Musik",
            "Opened": "Geöffnet", "Done": "Erledigt", "Rings at %@": "Klingelt um %@", "Today": "Heute",
            "Tomorrow": "Morgen", "Calendar": "Kalender", "To-do": "To-do", "Reminder": "Erinnerung",
            "Note written": "Notiz geschrieben", "Timer": "Timer", "Draft written": "Entwurf geschrieben",
            "Shows your reminders in the Milo window": "Zeigt deine Erinnerungen im Milo-Fenster",
            "Shows it": "Zeigt es", "Opens it": "Öffnet es", "Opens it in %@": "Öffnet es in %@",
            "Ready to copy": "Bereit zum Kopieren", "Written": "Geschrieben", "Written, ready to copy": "Geschrieben, bereit zum Kopieren",
            "On your clipboard": "In der Zwischenablage", "Copied": "Kopiert",
            "Alarm set": "Wecker gestellt", "Alarm": "Wecker",
            "Shows it in the Milo window, to copy": "Zeigt es im Milo-Fenster, zum Kopieren",
            "Sent": "Gesendet", "Called": "Angerufen", "Message sent": "Nachricht gesendet", "Call": "Anruf",
            "Sound": "Ton", "Screen": "Bildschirm",
        ]
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
    /// The conversation going on in the Milo window: text Milo wrote that waits there to be copied.
    case conversation
    /// Nowhere to go.
    case none

    public static func of(_ action: ActionDone) -> DonePlace {
        switch action.kind {
        case .reminder where action.app.isEmpty: return .today
        case .event: return .event(app: action.app.isEmpty ? "Calendar" : action.app, title: action.title,
                                   start: action.when)
        case .todo, .reminder: return .reminder(app: action.app.isEmpty ? "Reminders" : action.app, title: action.title)
        case .written: return action.app.isEmpty ? .conversation : .app(action.app)
        case .copied: return .conversation
        case .opened:
            // Only the detail, where the brain puts the address it opened: a title may be a file's name.
            if let page = page(action.detail) { return .page(page) }
            return action.app.isEmpty ? .none : .app(action.app)
        default:
            let app = action.app.isEmpty ? defaultApp[action.kind] ?? "" : action.app
            return app.isEmpty ? .none : .app(app)
        }
    }

    /// The app a kind lives in when the brain names none.
    static let defaultApp: [ActionDone.Kind: String] = [
        .note: "Notes", .draft: "Mail", .shortcut: "Shortcuts", .music: "Music", .timer: "Clock",
        .message: "Messages", .call: "FaceTime",
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
