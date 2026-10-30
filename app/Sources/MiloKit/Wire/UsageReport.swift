import Foundation

/// What the Usage page shows (`usage` in protocol/messages.json): every day of the range, where the tokens went,
/// which apps got the dictated words, and the accounts Milo works with. No dictated text.
public struct UsageReport: Equatable, Sendable, Decodable {
    /// Days in the range, ending today.
    public var span: Int
    /// YYYY-MM-DD on the brain's clock.
    public var today: String
    /// The first day anything was recorded, "" before that.
    public var since: String
    /// Every day of the range, oldest first.
    public var daily: [UsageDay]
    /// Tokens per kind of work, most first.
    public var sources: [UsageSource]
    /// Where dictations went, most words first.
    public var apps: [UsageApp]
    public var accounts: [UsageAccount]

    public init(span: Int, today: String, since: String = "", daily: [UsageDay], sources: [UsageSource] = [],
                apps: [UsageApp] = [], accounts: [UsageAccount] = []) {
        self.span = span
        self.today = today
        self.since = since
        self.daily = daily
        self.sources = sources
        self.apps = apps
        self.accounts = accounts
    }

    public var tokens: Int { daily.reduce(0) { $0 + $1.tokens } }
    public var cachedTokens: Int { daily.reduce(0) { $0 + $1.cachedInputTokens } }
    public var calls: Int { daily.reduce(0) { $0 + $1.calls } }
    public var dictations: Int { daily.reduce(0) { $0 + $1.dictations } }
    public var words: Int { daily.reduce(0) { $0 + $1.words } }
    /// Days with anything in them: a call or a dictation.
    public var activeDays: Int { daily.filter(\.active).count }

    /// Days in a row up to today with something in them; today may still be empty without breaking it.
    public var streak: Int {
        var days = daily.reversed().makeIterator()
        var count = 0
        if let last = days.next() {
            if last.active { count = 1 } else if daily.count == 1 { return 0 }
        }
        while let day = days.next(), day.active { count += 1 }
        return count
    }
}

public struct UsageDay: Equatable, Sendable, Decodable, Identifiable {
    /// YYYY-MM-DD.
    public var day: String
    public var calls: Int
    /// Includes the cached ones.
    public var inputTokens: Int
    public var cachedInputTokens: Int
    public var outputTokens: Int
    public var dictations: Int
    public var words: Int

    public var id: String { day }
    public var tokens: Int { inputTokens + outputTokens }
    public var active: Bool { calls > 0 || dictations > 0 }

    /// Local midnight of `day`, or nil if it isn't a date.
    public var date: Date? { UsageDay.parse(day) }

    public init(day: String, calls: Int = 0, inputTokens: Int = 0, cachedInputTokens: Int = 0, outputTokens: Int = 0,
                dictations: Int = 0, words: Int = 0) {
        self.day = day
        self.calls = calls
        self.inputTokens = inputTokens
        self.cachedInputTokens = cachedInputTokens
        self.outputTokens = outputTokens
        self.dictations = dictations
        self.words = words
    }

    enum CodingKeys: String, CodingKey {
        case day, calls, dictations, words
        case inputTokens = "input_tokens"
        case cachedInputTokens = "cached_input_tokens"
        case outputTokens = "output_tokens"
    }

    static func parse(_ day: String) -> Date? {
        let parts = day.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return Calendar.current.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }
}

public struct UsageSource: Equatable, Sendable, Decodable, Identifiable {
    /// "chat", "task", "memory", "proactive", or a newer kind.
    public var source: String
    public var calls: Int
    public var tokens: Int

    public var id: String { source }

    public init(source: String, calls: Int, tokens: Int) {
        self.source = source
        self.calls = calls
        self.tokens = tokens
    }

    /// What the user calls it.
    public var label: String {
        switch source {
        case "chat": "Talking with Milo"
        case "task": "Tasks he did for you"
        case "memory": "Keeping his memory tidy"
        case "proactive", "heartbeat": "Check-ins"
        default: source.capitalized
        }
    }
}

public struct UsageApp: Equatable, Sendable, Decodable, Identifiable {
    /// "" when Milo couldn't tell which app had the focus.
    public var app: String
    public var dictations: Int
    public var words: Int

    public var id: String { app }
    public var label: String { app.isEmpty ? "Unknown app" : app }

    public init(app: String, dictations: Int, words: Int) {
        self.app = app
        self.dictations = dictations
        self.words = words
    }
}

/// A service Milo uses, who it is signed in as, and what for.
public struct UsageAccount: Equatable, Sendable, Decodable, Identifiable {
    public enum State: String, Sendable, Decodable {
        case ok, signedOut = "signed_out", unknown, local
    }

    public var service: String
    /// What Milo uses it for, in plain words: "Talking", "Milo's voice".
    public var uses: [String]
    public var state: State
    /// "Max", "Free", "" when the service doesn't say.
    public var plan: String
    /// An email or account name, "" when the service doesn't say.
    public var who: String
    /// The model, the credits used, or why the plan can't be seen.
    public var detail: String

    public var id: String { service }

    public init(service: String, uses: [String], state: State = .ok, plan: String = "", who: String = "",
                detail: String = "") {
        self.service = service
        self.uses = uses
        self.state = state
        self.plan = plan
        self.who = who
        self.detail = detail
    }

    enum CodingKeys: String, CodingKey { case service, uses, state, plan, who, detail }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        service = try c.decode(String.self, forKey: .service)
        uses = try c.decodeIfPresent([String].self, forKey: .uses) ?? []
        state = State(rawValue: try c.decodeIfPresent(String.self, forKey: .state) ?? "") ?? .unknown
        plan = try c.decodeIfPresent(String.self, forKey: .plan) ?? ""
        who = try c.decodeIfPresent(String.self, forKey: .who) ?? ""
        detail = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""
    }
}
