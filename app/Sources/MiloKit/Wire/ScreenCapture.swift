/// What Milo saw in the frontmost window (`capture` in look_result and whats_this).
/// Only fields with text are sent. `error` says in plain words what couldn't be read.
public struct ScreenCapture: Equatable, Sendable {
    public var app: String
    public var window: String
    public var focused: String
    public var selection: String
    public var text: String
    /// Path of the screenshot PNG under ~/Milo/state/screens, "" without one.
    public var image: String
    public var error: String

    public init(app: String = "", window: String = "", focused: String = "", selection: String = "",
                text: String = "", image: String = "", error: String = "") {
        self.app = app
        self.window = window
        self.focused = focused
        self.selection = selection
        self.text = text
        self.image = image
        self.error = error
    }
}

extension ScreenCapture: Encodable {
    private enum Key: String, CodingKey {
        case app, window, focused, selection, text, image, error
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Key.self)
        for (key, value) in [(Key.app, app), (.window, window), (.focused, focused), (.selection, selection),
                             (.text, text), (.image, image), (.error, error)] where !value.isEmpty {
            try c.encode(value, forKey: key)
        }
    }
}

/// A point in global screen coordinates, in points with the origin at the top-left of the main display
/// (the way Accessibility and CGEvent count).
public struct ScreenPoint: Equatable, Sendable, Codable {
    public var x: Double
    public var y: Double

    public init(x: Double, y: Double) {
        self.x = x
        self.y = y
    }
}
