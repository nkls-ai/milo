import Foundation

/// One line of the conversation in the Milo window (`entry` in protocol/messages.json).
public struct TranscriptEntry: Equatable, Sendable, Identifiable {
    public enum Kind: String, Sendable {
        /// What the user said or typed.
        case user
        /// A reply from Milo.
        case milo
        /// Work handed to the worker agent, with its steps.
        case task
    }

    public enum Via: String, Sendable {
        case voice, typed
    }

    public let id: String
    public var date: Date
    public var kind: Kind
    public var text: String
    /// user: how it was said.
    public var via: Via
    /// milo: the face he made.
    public var emotion: Emotion
    /// milo: false while the reply still streams.
    public var done: Bool
    /// task: running, done or failed.
    public var status: ActivityStep.Status
    /// task: what Milo reported when it finished.
    public var result: String
    public var steps: [ActivityStep]

    public init(id: String, date: Date, kind: Kind, text: String, via: Via = .voice, emotion: Emotion = .neutral,
                done: Bool = true, status: ActivityStep.Status = .done, result: String = "",
                steps: [ActivityStep] = []) {
        self.id = id
        self.date = date
        self.kind = kind
        self.text = text
        self.via = via
        self.emotion = emotion
        self.done = done
        self.status = status
        self.result = result
        self.steps = steps
    }
}

/// One thing the worker agent did (`activity` in protocol/messages.json).
public struct ActivityStep: Equatable, Sendable, Identifiable {
    public enum Status: String, Sendable {
        case running, done, failed
    }

    public let id: String
    /// command, read, edit, search, web, tool, app or other. Picks the icon.
    public var kind: String
    /// Plain language, e.g. "Reading your Downloads folder".
    public var title: String
    /// The raw command or tool payload, shown when the row is expanded.
    public var detail: String
    public var status: Status

    public init(id: String, kind: String, title: String, detail: String = "", status: Status) {
        self.id = id
        self.kind = kind
        self.title = title
        self.detail = detail
        self.status = status
    }
}

extension TranscriptEntry: Decodable {
    private enum Key: String, CodingKey {
        case id, ts, kind, text, via, emotion, done, status, result, steps
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        date = Self.parseDate(try c.decode(String.self, forKey: .ts)) ?? Date()
        kind = Kind(rawValue: try c.decode(String.self, forKey: .kind)) ?? .milo
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
        via = Via(rawValue: try c.decodeIfPresent(String.self, forKey: .via) ?? "") ?? .voice
        emotion = Emotion(rawValue: try c.decodeIfPresent(String.self, forKey: .emotion) ?? "") ?? .neutral
        done = try c.decodeIfPresent(Bool.self, forKey: .done) ?? true
        status = ActivityStep.Status(rawValue: try c.decodeIfPresent(String.self, forKey: .status) ?? "") ?? .done
        result = try c.decodeIfPresent(String.self, forKey: .result) ?? ""
        steps = try c.decodeIfPresent([ActivityStep].self, forKey: .steps) ?? []
    }

    /// The brain sends local time without a zone, e.g. "2026-10-30T09:12:03".
    static func parseDate(_ text: String) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f.date(from: String(text.prefix(19)))
    }
}

extension ActivityStep: Decodable {
    private enum Key: String, CodingKey {
        case id, kind, title, detail, status
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        kind = try c.decodeIfPresent(String.self, forKey: .kind) ?? "other"
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        detail = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""
        status = Status(rawValue: try c.decodeIfPresent(String.self, forKey: .status) ?? "") ?? .done
    }
}
