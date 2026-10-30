import Foundation

/// Where an action is about to land, from the answer to `describe`: the point and the window around it.
/// Global points, origin top-left, like everything MacHands reports.
public struct HandsTarget: Equatable, Sendable {
    public var point: CGPoint?
    public var window: CGRect?
    public var pid: Int32?

    public init(point: CGPoint? = nil, window: CGRect? = nil, pid: Int32? = nil) {
        self.point = point
        self.window = window
        self.pid = pid
    }

    /// Reads `point` ({x, y}), `window` ({x, y, width, height}) and `pid`; anything missing stays nil.
    public init(describe result: [String: JSONValue]) {
        if case let .object(p)? = result["point"], let x = p["x"]?.number, let y = p["y"]?.number {
            point = CGPoint(x: x, y: y)
        }
        if case let .object(w)? = result["window"], let x = w["x"]?.number, let y = w["y"]?.number,
           let width = w["width"]?.number, let height = w["height"]?.number, width > 0, height > 0 {
            window = CGRect(x: x, y: y, width: width, height: height)
        }
        pid = result["pid"]?.number.map { Int32($0) }
    }

    /// A window frame as JSON, the way MacHands reports it.
    public static func json(_ frame: CGRect) -> JSONValue {
        .object(["x": .number(frame.minX), "y": .number(frame.minY),
                 "width": .number(frame.width), "height": .number(frame.height)])
    }
}
