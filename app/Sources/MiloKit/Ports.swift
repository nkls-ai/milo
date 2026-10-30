import Foundation

// Everything MiloController talks to. Each protocol has one real adapter in Adapters/
// and a fake in the tests; only main.swift names the adapters.

/// The connection to the brain. Callbacks arrive on the main queue.
public protocol BrainClient: AnyObject {
    var onEvent: ((BrainEvent) -> Void)? { get set }
    /// true when a connection comes up, false when it drops.
    var onConnectionChange: ((Bool) -> Void)? { get set }
    /// One connection attempt, closed again at once. true if a brain answers.
    func probe() -> Bool
    /// Connects and keeps reconnecting for the life of the app.
    func start()
    /// Dropped if not connected.
    func send(_ command: BrainCommand)
}

/// Starts and stops the brain process.
public protocol BrainLauncher: AnyObject {
    func start()
    func stop()
    func restart()
}

/// Puts text into the focused app.
public protocol TextInserter: AnyObject {
    func insert(_ text: String)
    /// Puts the text on the clipboard and leaves it there, for when pasting isn't allowed.
    func copy(_ text: String)
}

/// Keyboard events from every app. Callbacks arrive on the main queue.
public protocol KeyEventSource: AnyObject {
    var onEvent: ((KeyEvent) -> Void)? { get set }
    func start()
}

public struct AppContext: Equatable, Sendable {
    /// Name of the frontmost app, "" if none.
    public var app: String
    /// Seconds since the last keyboard or mouse input.
    public var idleSeconds: Double

    public init(app: String, idleSeconds: Double) {
        self.app = app
        self.idleSeconds = idleSeconds
    }
}

/// What the user is doing right now.
public protocol ContextProvider: AnyObject {
    /// Called on the main queue when another app comes to the front.
    var onAppSwitch: (() -> Void)? { get set }
    func current() -> AppContext
}

/// Work only Milo.app has permission for, asked by the brain (`app_request`): Calendar and Reminders.
/// Ops and their arguments are listed in docs/ARCHITECTURE.md.
public protocol AppConnections: AnyObject {
    /// `reply` must be called exactly once, on the main queue.
    func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void)
}

/// The Accessibility permission needed to see global keys and to paste.
public protocol AccessibilityPermission {
    /// With `prompt`, macOS shows its permission dialog if not yet trusted.
    func isTrusted(prompt: Bool) -> Bool
}

/// Reads the frontmost window: its text through Accessibility and a screenshot through ScreenCaptureKit.
public protocol ScreenReader: AnyObject {
    /// `selection`: the selected text alone if there is one, else the window. Completion on the main queue;
    /// a capture that failed has `error` set in plain words.
    func capture(selection: Bool, completion: @escaping (ScreenCapture) -> Void)
}

/// Runs the milo-mac actions inside the app, which holds the Accessibility and Screen Recording permissions.
public protocol HandsExecutor: AnyObject {
    /// One action (a milo-mac tool, or "describe"). Completion on the main queue.
    func perform(_ tool: String, args: [String: JSONValue],
                 completion: @escaping (Result<[String: JSONValue], HandsFailure>) -> Void)
    /// Stop what is still running, e.g. an AppleScript.
    func cancel()
    /// The user lent the real mouse and keyboard. Without it, an action that can't be done in the background
    /// fails with `HandsFailure.borrow` and touches nothing.
    var borrowed: Bool { get set }
}

public struct HandsFailure: Error, Equatable, Sendable {
    /// Plain words for the worker agent, e.g. "There is no element e9. Call ax_tree again."
    public let message: String
    /// "mouse" or "keyboard" when the action needs the real one, which the user must lend first.
    public let borrow: String?

    public init(_ message: String, borrow: String? = nil) {
        self.message = message
        self.borrow = borrow
    }
}

/// Milo's own pointer, drawn over everything. It never moves the user's. Points are AppKit global coordinates.
public protocol CursorDisplay: AnyObject {
    /// Glide to where Milo is about to act. `arrived` runs once it is there, on the main queue.
    func glide(to point: CGPoint, arrived: @escaping () -> Void)
    /// A click landed here: a small ripple.
    func click(at point: CGPoint)
    /// Milo types here: a caret and a hint.
    func typing(at point: CGPoint)
    /// The work is over: fade out.
    func rest()
}

/// Follows a window of another app while Milo works in it. Frames are global points, origin top-left.
public protocol WindowWatcher: AnyObject {
    /// Watch the window of `pid` with this frame; `changed` gets its new frame on every move or resize, and nil
    /// once it closes. Replaces the window watched before.
    func watch(pid: Int32, frame: CGRect, changed: @escaping (CGRect?) -> Void)
    func stop()
}

/// For a screen without Milo's cursor (tests, or before the overlay exists).
public final class NoCursor: CursorDisplay {
    public init() {}
    public func glide(to point: CGPoint, arrived: @escaping () -> Void) { arrived() }
    public func click(at point: CGPoint) {}
    public func typing(at point: CGPoint) {}
    public func rest() {}
}

public final class NoWindowWatcher: WindowWatcher {
    public init() {}
    public func watch(pid: Int32, frame: CGRect, changed: @escaping (CGRect?) -> Void) {}
    public func stop() {}
}

/// Mouse and keyboard input from every app while the worker acts. Callbacks on the main queue.
public protocol UserInputSource: AnyObject {
    var onInput: ((UserInput) -> Void)? { get set }
    func start()
    func stop()
}

/// A global shortcut that works without focus, for "What's this?".
public protocol HotkeySource: AnyObject {
    var onPress: (() -> Void)? { get set }
    /// nil removes it. Returns false if macOS refused, e.g. another app holds the combo.
    @discardableResult func register(_ combo: KeyCombo?) -> Bool
}
