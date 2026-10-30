/// Milo by message, for the menu (`remote` in protocol/messages.json).
public struct RemoteStatus: Equatable, Sendable, Decodable {
    public enum State: String, Sendable, Decodable {
        /// Checking the chat app's token or permissions.
        case starting
        /// No phone yet; `detail` says how to connect one.
        case unpaired
        /// A phone is connected; `detail` is its owner's name in the chat app.
        case paired
        /// The chat app can't be reached or refused Milo; `detail` says why.
        case error
    }

    /// The chat app's name, e.g. "telegram".
    public var channel: String
    /// What the user calls it, e.g. "Telegram".
    public var label: String
    public var state: State
    /// The menu's "Pause messages from your phone".
    public var paused: Bool
    public var detail: String

    public init(channel: String, label: String, state: State, paused: Bool = false, detail: String = "") {
        self.channel = channel
        self.label = label
        self.state = state
        self.paused = paused
        self.detail = detail
    }

    private enum Key: String, CodingKey { case channel, label, state, paused, detail }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        channel = try c.decode(String.self, forKey: .channel)
        label = try c.decode(String.self, forKey: .label)
        state = State(rawValue: try c.decode(String.self, forKey: .state)) ?? .error
        paused = try c.decodeIfPresent(Bool.self, forKey: .paused) ?? false
        detail = try c.decodeIfPresent(String.self, forKey: .detail) ?? ""
    }

    /// One line for the menu, like "Telegram: connected (Niklas)".
    public var summary: String {
        switch state {
        case .starting: return "\(label): starting…"
        case .unpaired: return "\(label): no phone connected yet"
        case .paired: return "\(label): \(paused ? "paused" : "connected")" + (detail.isEmpty ? "" : " (\(detail))")
        case .error: return "\(label): not working"
        }
    }
}
