/// Milo did one everyday thing himself, at once, from the brain's `action_done` event (ADR 0029): put an event in,
/// added a to-do, set a timer, opened an app. For the card that shows it.
public struct ActionDone: Equatable, Sendable, Decodable {
    /// event, todo, reminder, note, timer, draft, shortcut, music or opened. A kind a newer brain invents still
    /// decodes: show it plainly.
    public let kind: String
    public let title: String
    public let detail: String
    /// Local time, "2026-11-05T15:00", for what has one; nil otherwise.
    public let when: String?
    /// The app it happened in ("Calendar"), nil when the brain left it out.
    public let app: String?
    /// The task id `undo_task` takes it back with; nil when it can't be undone.
    public let undo: String?

    public init(kind: String, title: String, detail: String = "", when: String? = nil, app: String? = nil,
                undo: String? = nil) {
        self.kind = kind
        self.title = title
        self.detail = detail
        self.when = when
        self.app = app
        self.undo = undo
    }

    private enum Key: String, CodingKey { case kind, title, detail, when, app, undo }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        kind = try c.decode(String.self, forKey: .kind)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        detail = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""
        func optional(_ key: Key) throws -> String? {
            guard let text = try c.decodeIfPresent(String.self, forKey: key), !text.isEmpty else { return nil }
            return text
        }
        when = try optional(.when)
        app = try optional(.app)
        undo = try optional(.undo)
    }
}
