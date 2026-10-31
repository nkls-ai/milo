/// A task Milo can take back, from the brain's `undo_points` event (ADR 0024).
public struct UndoPoint: Equatable, Sendable, Identifiable, Decodable {
    public enum State: String, Sendable, Decodable {
        case ready, undoing, undone
    }

    /// The task's transcript entry.
    public let id: String
    public let title: String
    public let state: State
    /// What Milo said when the task finished, so the bubble saying it can carry the Undo button.
    public let said: String

    public init(id: String, title: String, state: State = .ready, said: String = "") {
        self.id = id
        self.title = title
        self.state = state
        self.said = said
    }

    private enum Key: String, CodingKey { case id, title, state, said }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        // A state a newer brain invents shows no button rather than a wrong one.
        state = State(rawValue: try c.decodeIfPresent(String.self, forKey: .state) ?? "") ?? .undoing
        said = try c.decodeIfPresent(String.self, forKey: .said) ?? ""
    }
}
