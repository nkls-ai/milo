/// One of the small helpers working for Milo, from the brain's `helpers` event.
public struct HelperInfo: Equatable, Sendable, Identifiable, Decodable {
    public enum Status: String, Sendable, Decodable {
        case queued, working, done, failed, stopped
        case needsYou = "needs_you"

        /// Still to do or under way, so it gets a bird and a Stop button.
        public var active: Bool { self == .queued || self == .working || self == .needsYou }
    }

    /// The transcript entry of its task, so the Milo window can show it.
    public let id: String
    /// Short and plain: "Budget table in Excel".
    public let title: String
    public let status: Status
    /// What it is doing right now, in plain words. Empty once it is done.
    public let step: String
    /// 0...1 through the helper's own to-do list; nil while it has none.
    public let progress: Double?

    public init(id: String, title: String, status: Status, step: String = "", progress: Double? = nil) {
        self.id = id
        self.title = title
        self.status = status
        self.step = step
        self.progress = progress
    }

    private enum Key: String, CodingKey { case id, title, status, step, progress }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        // A status a newer brain invents still shows as a helper at work.
        status = Status(rawValue: try c.decodeIfPresent(String.self, forKey: .status) ?? "") ?? .working
        step = try c.decodeIfPresent(String.self, forKey: .step) ?? ""
        progress = try c.decodeIfPresent(Double.self, forKey: .progress).map { min(1, max(0, $0)) }
    }
}
