import Foundation

/// Push-to-talk on modifier keys, like Wispr Flow. Pure: feed it key events and expired deadlines,
/// act on what it returns.
///
/// Holding a bound key records while it is held. Recording starts the moment the key goes down, but
/// tentatively: the brain records without showing anything until the hold passes `minHold` (`confirm`),
/// so a stray tap never makes Milo flicker. Any other key or modifier during a hold cancels, so normal
/// shortcuts (⌥-letter, fn-arrows) still work. Pressing the other bound key during a hold is ignored.
///
/// Two short taps of the same key within `doubleTap` lock the mode on, hands-free (`lock`). The
/// recording that the first tap started simply continues. A further press of that key stops, `esc`
/// cancels, and after `maxLocked` it stops by itself. Other keys don't cancel a locked recording:
/// the user isn't typing while dictating, and Milo's own pastes would otherwise end it.
public struct PushToTalk: Sendable {
    public enum Output: Equatable, Sendable {
        /// A bound key went down: record, but show nothing yet. It may turn out to be a tap.
        case start(ListenMode)
        /// The hold is real: show the recording.
        case confirm(ListenMode)
        /// A double tap locked the recording on: show it.
        case lock(ListenMode)
        case stop(ListenMode)
        case cancel(ListenMode)
    }

    private enum Phase: Equatable, Sendable {
        case idle
        /// The key is down since `since`. `second`: this press may complete a double tap.
        case holding(ListenMode, since: TimeInterval, second: Bool, confirmed: Bool)
        /// One short tap; a second press before `until` makes it a double tap.
        case tapped(ListenMode, until: TimeInterval)
        case locked(ListenMode, until: TimeInterval)
    }

    public private(set) var bindings: HotkeyBindings
    public let minHold: TimeInterval
    public let doubleTap: TimeInterval
    public var maxLocked: TimeInterval
    private var phase: Phase = .idle

    public init(bindings: HotkeyBindings = .default, minHold: TimeInterval = 0.25, doubleTap: TimeInterval = 0.35,
                maxLocked: TimeInterval = 300) {
        self.bindings = bindings
        self.minHold = minHold
        self.doubleTap = doubleTap
        self.maxLocked = maxLocked
    }

    /// The mode being recorded, shown or not.
    public var active: ListenMode? {
        switch phase {
        case .idle: nil
        case let .holding(mode, _, _, _), let .tapped(mode, _), let .locked(mode, _): mode
        }
    }

    /// The mode locked on by a double tap.
    public var locked: ListenMode? {
        if case let .locked(mode, _) = phase { mode } else { nil }
    }

    /// When `expire(at:)` must be called next, on the key events' clock. nil: no timer needed.
    public var deadline: TimeInterval? {
        switch phase {
        case .idle, .holding(_, _, _, confirmed: true): nil
        case let .holding(_, since, _, _): since + minHold
        case let .tapped(_, until), let .locked(_, until): until
        }
    }

    public mutating func handle(_ event: KeyEvent) -> [Output] {
        let time = event.timestamp
        switch event.kind {
        case .escape:
            return cancel()
        case .keyDown:
            if case .locked = phase { return [] }
            return cancel()
        case let .modifierChanged(keyCode, isDown):
            guard let mode = bindings.mode(forKeyCode: keyCode) else {
                // Another modifier joined the chord: it's a shortcut, not push-to-talk.
                if case .locked = phase { return [] }
                return cancel()
            }
            return isDown ? press(mode, at: time) : release(mode, at: time)
        }
    }

    /// Call when `deadline` has passed. `time` is on the key events' clock.
    public mutating func expire(at time: TimeInterval) -> [Output] {
        guard let deadline, time >= deadline else { return [] }
        switch phase {
        case let .holding(mode, since, second, _):
            phase = .holding(mode, since: since, second: second, confirmed: true)
            return [.confirm(mode)]
        case let .tapped(mode, _):
            phase = .idle
            return [.cancel(mode)]
        case let .locked(mode, _):
            phase = .idle
            return [.stop(mode)]
        case .idle:
            return []
        }
    }

    /// Switches to new bindings. A recording in progress is cancelled, since its key may no longer be bound.
    public mutating func rebind(_ new: HotkeyBindings) -> [Output] {
        guard new != bindings else { return [] }
        bindings = new
        return cancel()
    }

    /// Forgets any recording, e.g. when the brain went away.
    public mutating func reset() -> [Output] {
        cancel()
    }

    private mutating func press(_ mode: ListenMode, at time: TimeInterval) -> [Output] {
        switch phase {
        case .idle:
            phase = .holding(mode, since: time, second: false, confirmed: false)
            return [.start(mode)]
        case let .tapped(current, until) where current == mode:
            // The recording the first tap started goes on. A late second press is a fresh hold.
            phase = .holding(mode, since: time, second: time < until, confirmed: false)
            return []
        case let .tapped(current, _):
            phase = .holding(mode, since: time, second: false, confirmed: false)
            return [.cancel(current), .start(mode)]
        case let .locked(current, _) where current == mode:
            phase = .idle
            return [.stop(mode)]
        case .holding, .locked:
            return []
        }
    }

    private mutating func release(_ mode: ListenMode, at time: TimeInterval) -> [Output] {
        guard case let .holding(current, since, second, confirmed) = phase, current == mode else { return [] }
        if confirmed || time - since >= minHold {
            phase = .idle
            return [.stop(mode)]
        }
        if second {
            phase = .locked(mode, until: time + maxLocked)
            return [.lock(mode)]
        }
        phase = .tapped(mode, until: since + doubleTap)
        return []
    }

    private mutating func cancel() -> [Output] {
        guard let mode = active else { return [] }
        phase = .idle
        return [.cancel(mode)]
    }
}
