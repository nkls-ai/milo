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

/// The Accessibility permission needed to see global keys and to paste.
public protocol AccessibilityPermission {
    /// With `prompt`, macOS shows its permission dialog if not yet trusted.
    func isTrusted(prompt: Bool) -> Bool
}
