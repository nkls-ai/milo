import Foundation

/// One of the user's routines, from the brain's `routines` event: a recipe Milo keeps in ~/Milo/routines.
public struct RoutineInfo: Equatable, Sendable, Identifiable, Decodable {
    /// The file name without .md, used in `routine` commands.
    public let id: String
    public let name: String
    public let description: String
    /// In plain words, "every Monday at 09:00"; empty without a schedule.
    public let schedule: String
    public let paused: Bool
    /// "2026-10-26 09:00, done"; empty before the first run.
    public let lastRun: String
    /// When the schedule runs it next; nil without one, or while paused.
    public let nextRun: Date?
    /// The names of the values that change between runs, like "month".
    public let inputs: [String]
    /// The file doesn't read, or its schedule doesn't, in plain words. nil when all is well.
    public let problem: String?

    public init(id: String, name: String, description: String = "", schedule: String = "", paused: Bool = false,
                lastRun: String = "", nextRun: Date? = nil, inputs: [String] = [], problem: String? = nil) {
        self.id = id
        self.name = name
        self.description = description
        self.schedule = schedule
        self.paused = paused
        self.lastRun = lastRun
        self.nextRun = nextRun
        self.inputs = inputs
        self.problem = problem
    }

    private enum Key: String, CodingKey {
        case id, name, description, schedule, paused, inputs, problem
        case lastRun = "last_run"
        case nextRun = "next_run"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? id
        description = try c.decodeIfPresent(String.self, forKey: .description) ?? ""
        schedule = try c.decodeIfPresent(String.self, forKey: .schedule) ?? ""
        paused = try c.decodeIfPresent(Bool.self, forKey: .paused) ?? false
        lastRun = try c.decodeIfPresent(String.self, forKey: .lastRun) ?? ""
        nextRun = try c.decodeIfPresent(String.self, forKey: .nextRun).flatMap(Self.parseTime)
        inputs = try c.decodeIfPresent([String].self, forKey: .inputs) ?? []
        problem = try c.decodeIfPresent(String.self, forKey: .problem)
    }

    /// The brain sends local time without a zone or seconds, e.g. "2026-11-02T09:00".
    static func parseTime(_ text: String) -> Date? {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd'T'HH:mm"
        return f.date(from: String(text.prefix(16)))
    }
}

/// A recipe Milo wrote down and the user hasn't saved yet: shown whole, with Save and "Change it".
public struct RoutineDraft: Equatable, Sendable, Identifiable, Decodable {
    public let id: String
    public let name: String
    /// The whole file, front matter and all, as it would be saved.
    public let recipe: String
    public let schedule: String

    public init(id: String, name: String, recipe: String, schedule: String = "") {
        self.id = id
        self.name = name
        self.recipe = recipe
        self.schedule = schedule
    }

    private enum Key: String, CodingKey { case id, name, recipe, schedule }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        recipe = try c.decodeIfPresent(String.self, forKey: .recipe) ?? ""
        schedule = try c.decodeIfPresent(String.self, forKey: .schedule) ?? ""
    }

    /// The recipe without its front matter: what a person reads to check it.
    public var steps: String {
        let lines = recipe.components(separatedBy: "\n")
        guard lines.first?.trimmingCharacters(in: .whitespaces) == "---",
              let end = lines.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" })
        else { return recipe.trimmingCharacters(in: .whitespacesAndNewlines) }
        return lines[(end + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// The input lines of the front matter, as "month: Which month? (last month)".
    public var inputs: [String] {
        var out: [String] = []
        var current: (name: String, ask: String, fallback: String)?
        var inInputs = false
        func flush() {
            if let c = current {
                out.append(c.name + (c.ask.isEmpty ? "" : ": \(c.ask)") + (c.fallback.isEmpty ? "" : " (\(c.fallback))"))
            }
            current = nil
        }
        for line in recipe.components(separatedBy: "\n").dropFirst() {
            if line.trimmingCharacters(in: .whitespaces) == "---" { break }
            if !line.hasPrefix(" ") { flush(); inInputs = line.hasPrefix("inputs:"); continue }
            guard inInputs else { continue }
            let text = line.trimmingCharacters(in: .whitespaces)
            if text.hasPrefix("- name:") {
                flush()
                current = (Self.value(text.dropFirst(7)), "", "")
            } else if text.hasPrefix("ask:") {
                current?.ask = Self.value(text.dropFirst(4))
            } else if text.hasPrefix("default:") {
                current?.fallback = Self.value(text.dropFirst(8))
            }
        }
        flush()
        return out
    }

    private static func value(_ text: Substring) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        if trimmed.count >= 2, trimmed.hasPrefix("\""), trimmed.hasSuffix("\""),
           let data = trimmed.data(using: .utf8), let decoded = try? JSONDecoder().decode(String.self, from: data) {
            return decoded
        }
        return trimmed
    }
}

/// What a button in the Routines section asks the brain to do (`routine` in protocol/messages.json).
public enum RoutineAction: String, Sendable, Codable {
    case run, pause, resume, delete
}
