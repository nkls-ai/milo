import Foundation

/// One thing Milo knows about the user, from the brain's `facts` event.
public struct MemoryFact: Equatable, Sendable, Identifiable, Decodable {
    public let id: String
    public let text: String
    /// basics, people, work, preferences, routines or learned.
    public let topic: String
    /// When Milo learned it, as the brain wrote it.
    public let since: String
    /// Always in Milo's mind (the basics, or pinned): it goes with every conversation.
    public let pinned: Bool

    public init(id: String, text: String, topic: String, since: String, pinned: Bool = false) {
        self.id = id
        self.text = text
        self.topic = topic
        self.since = since
        self.pinned = pinned
    }

    private enum Key: String, CodingKey { case id, text, topic, since, pinned }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        text = try c.decode(String.self, forKey: .text)
        topic = try c.decodeIfPresent(String.self, forKey: .topic) ?? "learned"
        since = try c.decodeIfPresent(String.self, forKey: .since) ?? ""
        pinned = try c.decodeIfPresent(Bool.self, forKey: .pinned) ?? false
    }
}

/// What the "What Milo knows" window shows: the brain's facts, grouped by topic. Updated on the main queue.
public final class KnowledgeModel: ObservableObject {
    @Published public private(set) var facts: [MemoryFact] = []
    /// False until the brain answered once, so the window can say it is still asking.
    @Published public private(set) var loaded = false

    public init(facts: [MemoryFact] = [], loaded: Bool = false) {
        self.facts = facts
        self.loaded = loaded
    }

    public func apply(_ event: BrainEvent) {
        guard case let .facts(list) = event else { return }
        facts = list
        loaded = true
    }

    public struct Group: Equatable, Identifiable {
        public let topic: String
        public let title: String
        public let facts: [MemoryFact]
        public var id: String { topic }
    }

    /// The same headings as profile.md, in the same order; a topic the app doesn't know comes last.
    public static let topics: [(topic: String, title: String)] = [
        ("basics", "Basics"), ("people", "People"), ("work", "Work and projects"), ("preferences", "Preferences"),
        ("routines", "Routines"), ("learned", "Learned"),
    ]

    public var groups: [Group] {
        let known = Self.topics.map(\.topic)
        let others = Array(Set(facts.map(\.topic)).subtracting(known)).sorted()
        return (Self.topics + others.map { ($0, $0.capitalized) }).compactMap { topic, title in
            let inTopic = facts.filter { $0.topic == topic }
            return inTopic.isEmpty ? nil : Group(topic: topic, title: title, facts: inTopic)
        }
    }
}
