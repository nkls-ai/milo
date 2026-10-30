import Foundation

/// A conversation's header in the Milo window's list (`conversations` in protocol/messages.json).
/// See docs/design/conversations.md.
public struct ConversationInfo: Equatable, Sendable, Identifiable, Decodable {
    public enum Kind: String, Sendable, Decodable {
        /// Talking with Milo, at the Mac or from the phone.
        case chat
        /// A routine that ran on its schedule.
        case routine
        /// A meeting's notes.
        case meeting
    }

    public let id: String
    public var kind: Kind
    public var started: Date
    public var last: Date
    /// Short, by Milo or the user: "Photos from Friday".
    public var title: String
    /// "words" (from the first thing said), "milo" or "you".
    public var titledBy: String
    /// How the user's turns came: voice, typed, message (the phone).
    public var via: [TranscriptEntry.Via]
    /// User turns.
    public var turns: Int
    /// Milo's latest line, short.
    public var preview: String
    public var tasks: [TaskSummary]
    /// "meeting:<id>" or "routine:<name>" for conversations of their own.
    public var source: String

    public init(id: String, kind: Kind = .chat, started: Date, last: Date? = nil, title: String,
                titledBy: String = "milo", via: [TranscriptEntry.Via] = [], turns: Int = 0, preview: String = "",
                tasks: [TaskSummary] = [], source: String = "") {
        self.id = id
        self.kind = kind
        self.started = started
        self.last = last ?? started
        self.title = title
        self.titledBy = titledBy
        self.via = via
        self.turns = turns
        self.preview = preview
        self.tasks = tasks
        self.source = source
    }

    /// Some of it came from the phone.
    public var fromPhone: Bool { via.contains(.message) }
    /// A task in it is still at work.
    public var working: Bool { tasks.contains { $0.status == .running } }

    private enum Key: String, CodingKey {
        case id, kind, started, last, title, via, turns, preview, tasks, source
        case titledBy = "titled_by"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        kind = Kind(rawValue: try c.decodeIfPresent(String.self, forKey: .kind) ?? "") ?? .chat
        started = TranscriptEntry.parseDate(try c.decode(String.self, forKey: .started)) ?? Date()
        last = TranscriptEntry.parseDate(try c.decodeIfPresent(String.self, forKey: .last) ?? "") ?? started
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        titledBy = try c.decodeIfPresent(String.self, forKey: .titledBy) ?? "words"
        via = (try c.decodeIfPresent([String].self, forKey: .via) ?? []).compactMap(TranscriptEntry.Via.init(rawValue:))
        turns = try c.decodeIfPresent(Int.self, forKey: .turns) ?? 0
        preview = try c.decodeIfPresent(String.self, forKey: .preview) ?? ""
        tasks = try c.decodeIfPresent([TaskSummary].self, forKey: .tasks) ?? []
        source = try c.decodeIfPresent(String.self, forKey: .source) ?? ""
    }
}

/// A task in a conversation's header: enough for the list and Today without opening it.
public struct TaskSummary: Equatable, Sendable, Identifiable, Decodable {
    public let id: String
    public var title: String
    public var status: ActivityStep.Status
    public var date: Date

    public init(id: String, title: String, status: ActivityStep.Status, date: Date) {
        self.id = id
        self.title = title
        self.status = status
        self.date = date
    }

    private enum Key: String, CodingKey { case id, title, status, at }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        status = ActivityStep.Status(rawValue: try c.decodeIfPresent(String.self, forKey: .status) ?? "") ?? .done
        date = TranscriptEntry.parseDate(try c.decodeIfPresent(String.self, forKey: .at) ?? "") ?? Date()
    }
}

/// One conversation search found (`search_results`).
public struct SearchHit: Equatable, Sendable, Identifiable, Decodable {
    public var id: String { conversation }
    public let conversation: String
    public var title: String
    public var kind: ConversationInfo.Kind
    public var date: Date
    /// The words around what matched.
    public var snippet: String
    public var via: [TranscriptEntry.Via]

    public init(conversation: String, title: String, kind: ConversationInfo.Kind = .chat, date: Date,
                snippet: String = "", via: [TranscriptEntry.Via] = []) {
        self.conversation = conversation
        self.title = title
        self.kind = kind
        self.date = date
        self.snippet = snippet
        self.via = via
    }

    private enum Key: String, CodingKey { case conversation, title, kind, at, snippet, via }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        conversation = try c.decode(String.self, forKey: .conversation)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        kind = ConversationInfo.Kind(rawValue: try c.decodeIfPresent(String.self, forKey: .kind) ?? "") ?? .chat
        date = TranscriptEntry.parseDate(try c.decodeIfPresent(String.self, forKey: .at) ?? "") ?? Date()
        snippet = try c.decodeIfPresent(String.self, forKey: .snippet) ?? ""
        via = (try c.decodeIfPresent([String].self, forKey: .via) ?? []).compactMap(TranscriptEntry.Via.init(rawValue:))
    }
}

/// An open reminder of today or tomorrow, for Today (`reminders`).
public struct ReminderItem: Equatable, Sendable, Decodable {
    public var due: Date
    public var text: String

    public init(due: Date, text: String) {
        self.due = due
        self.text = text
    }

    private enum Key: String, CodingKey { case due, text }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        due = RoutineInfo.parseTime(try c.decode(String.self, forKey: .due)) ?? Date()
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
    }
}
