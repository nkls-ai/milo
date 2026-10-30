import Foundation

/// Mouse or keyboard input while the worker acts on screen, as takeover detection sees it.
public struct UserInput: Equatable, Sendable {
    public enum Kind: Equatable, Sendable {
        /// The pointer moved to this point (global, top-left origin).
        case mouseMoved(x: Double, y: Double)
        case mouseDown
        case scroll
        /// Any key other than esc.
        case key
        case escape
    }

    public var kind: Kind
    /// Seconds on a monotonic clock (NSEvent.timestamp in the app).
    public var timestamp: TimeInterval
    /// Posted by Milo himself: its source user data is PasteboardInserter.eventMarker.
    public var synthetic: Bool

    public init(_ kind: Kind, at timestamp: TimeInterval, synthetic: Bool = false) {
        self.kind = kind
        self.timestamp = timestamp
        self.synthetic = synthetic
    }
}

/// Decides when the user takes the Mac back from the worker. Pure: it only sees inputs and timestamps.
///
/// Milo's own events carry a marker and never count. Pressing a key, clicking or scrolling stops the
/// session at once, esc always does. The pointer counts only once it moved more than `slop` points from
/// where it rested, and not within `grace` seconds of an action of Milo's: moving the pointer for a click
/// can show up as an unmarked move.
public struct TakeoverDetector: Sendable {
    public enum Reason: String, Sendable {
        case escape, user
    }

    public var grace: TimeInterval
    public var slop: Double
    public private(set) var armed = false
    private var actingUntil: TimeInterval = -.infinity
    private var anchor: (x: Double, y: Double)?

    public init(grace: TimeInterval = 0.3, slop: Double = 6) {
        self.grace = grace
        self.slop = slop
    }

    /// Start watching, e.g. when the session starts or a question is answered.
    public mutating func arm() {
        armed = true
        anchor = nil
    }

    public mutating func disarm() {
        armed = false
    }

    /// Milo starts or finishes an action at `time`.
    public mutating func miloActs(at time: TimeInterval) {
        actingUntil = max(actingUntil, time + grace)
        anchor = nil
    }

    /// The reason to stop now, or nil to carry on.
    public mutating func handle(_ input: UserInput) -> Reason? {
        guard armed, !input.synthetic else { return nil }
        switch input.kind {
        case .escape:
            return .escape
        case .key, .mouseDown, .scroll:
            return .user
        case let .mouseMoved(x, y):
            if input.timestamp <= actingUntil {
                anchor = (x, y)
                return nil
            }
            guard let rest = anchor else {
                anchor = (x, y)
                return nil
            }
            return hypot(x - rest.x, y - rest.y) > slop ? .user : nil
        }
    }
}
