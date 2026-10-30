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
/// Esc always stops. In the background (`mode == .background`) that is all: Milo acts on his window without
/// the user's pointer or keyboard, so the user keeps working and nothing they do stops him. While he borrows
/// the mouse or keyboard (`.borrowed`), Milo's own events carry a marker and never count, and pressing a
/// key, clicking or scrolling stops the session at once. The pointer counts only once it moved more than
/// `slop` points from where it rested, and not within `grace` seconds of an action of Milo's: moving the
/// pointer for a click can show up as an unmarked move.
public struct TakeoverDetector: Sendable {
    public enum Reason: String, Sendable {
        case escape, user
    }

    public enum Mode: Sendable {
        case background, borrowed
    }

    public var grace: TimeInterval
    public var slop: Double
    /// Switching to `.borrowed` forgets where the pointer rested, so the switch itself never counts as a move.
    public var mode: Mode {
        didSet { if mode != oldValue { anchor = nil } }
    }
    public private(set) var armed = false
    private var actingUntil: TimeInterval = -.infinity
    private var anchor: (x: Double, y: Double)?

    public init(grace: TimeInterval = 0.3, slop: Double = 6, mode: Mode = .borrowed) {
        self.grace = grace
        self.slop = slop
        self.mode = mode
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
        if case .escape = input.kind { return .escape }
        guard mode == .borrowed else { return nil }
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
