import Foundation

/// Something small Milo just did for the user, from the brain's `action_done` event: a calendar event, a to-do, a
/// reminder, a note, a timer, a draft, a shortcut, music, a page he opened or text he wrote for the user. The overlay
/// shows it as a card that comes out of Milo (`DoneCards`).
public struct ActionDone: Equatable, Sendable, Decodable {
    public enum Kind: String, Sendable, Decodable, CaseIterable {
        case event, todo, reminder, note, timer, draft, shortcut, music, opened
        /// One of Milo's alarms (`<alarm>`, ADR 0038): `when` is when it rings.
        case alarm
        /// Text Milo wrote (`<write>`, ADR 0033): pasted into `app`, or, with no app, waiting in his window to copy.
        case written
        /// Text Milo put on the clipboard (`<copy>`): a link, an address, a code the user asked for.
        case copied
        /// A text message Milo sent, after the user's yes (ADR 0039): the detail is what it said.
        case message
        /// A call Milo started, after the user's yes (ADR 0039): the detail is the number or address.
        case call
        /// The sound volume (`<volume>`) and the screen's brightness (`<brightness>`), ADR 36.
        case sound, brightness
        /// A kind a newer brain invents: a plain card with a check.
        case other
    }

    public let kind: Kind
    /// What it is called: "Dentist", "Buy milk", "youtube.com".
    public let title: String
    /// One plain line more (a place, a list, a song), or "".
    public let detail: String
    /// An event's start, a reminder's due time, a timer's end, when an alarm rings. nil when it has none.
    public let when: Date?
    /// The app it lives in ("Calendar", "Reminders", "Notes", "Mail", "Safari"); "" for Milo's own reminders.
    public let app: String
    /// The task whose Undo takes it back (`undo_task`, ADR 0026); "" when there is none.
    public let undo: String
    /// The language Milo said it in ("en", "de"), which the title is in: the card's own words follow it. "" when the
    /// brain didn't say; then they follow the system's.
    public let lang: String

    public init(kind: Kind, title: String, detail: String = "", when: Date? = nil, app: String = "", undo: String = "",
                lang: String = "") {
        self.kind = kind
        self.title = title
        self.detail = detail
        self.when = when
        self.app = app
        self.undo = undo
        self.lang = lang
    }

    private enum Key: String, CodingKey { case kind, title, detail, when, app, undo, lang }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        kind = Kind(rawValue: try c.decodeIfPresent(String.self, forKey: .kind) ?? "") ?? .other
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        detail = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""
        when = try c.decodeIfPresent(String.self, forKey: .when).flatMap(Self.time)
        app = try c.decodeIfPresent(String.self, forKey: .app) ?? ""
        undo = try c.decodeIfPresent(String.self, forKey: .undo) ?? ""
        lang = try c.decodeIfPresent(String.self, forKey: .lang) ?? ""
    }

    /// An ISO time with a zone ("2026-11-05T15:00:00+01:00", "…Z"), or local time without one ("2026-11-05T15:00").
    static func time(_ text: String) -> Date? {
        guard !text.isEmpty else { return nil }
        let zoned = ISO8601DateFormatter()
        if let date = zoned.date(from: text) { return date }
        zoned.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return zoned.date(from: text) ?? RoutineInfo.parseTime(text)
    }
}
