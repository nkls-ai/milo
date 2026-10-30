import Foundation

/// A keyboard event as push-to-talk sees it.
public struct KeyEvent: Equatable, Sendable {
    public enum Kind: Equatable, Sendable {
        /// A modifier key went down or up.
        case modifierChanged(keyCode: UInt16, isDown: Bool)
        /// Any ordinary key other than esc was pressed.
        case keyDown
        /// esc was pressed. Cancels a hold like any key, and also a locked recording.
        case escape
    }

    public var kind: Kind
    /// Seconds on a monotonic clock (NSEvent.timestamp in the app).
    public var timestamp: TimeInterval

    /// Virtual key code of esc.
    public static let escapeKeyCode: UInt16 = 53

    public init(_ kind: Kind, at timestamp: TimeInterval) {
        self.kind = kind
        self.timestamp = timestamp
    }

    /// A key-down event.
    public static func keyDown(keyCode: UInt16, at timestamp: TimeInterval) -> KeyEvent {
        KeyEvent(keyCode == escapeKeyCode ? .escape : .keyDown, at: timestamp)
    }

    /// A flags-changed event: the key counts as down if its own modifier bit is set in `flags`
    /// (see `ModifierFlag.isDown`).
    public static func flagsChanged(keyCode: UInt16, flags: UInt, at timestamp: TimeInterval) -> KeyEvent {
        KeyEvent(.modifierChanged(keyCode: keyCode, isDown: ModifierFlag.isDown(keyCode: keyCode, flags: flags)),
                 at: timestamp)
    }
}
