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

/// The text field that has the keyboard focus in another app, as Accessibility reads it.
public struct FocusedText: Equatable, Sendable {
    /// The same number for the same field while it exists; another field gets another.
    public var field: Int
    public var value: String
    /// Where the caret is (the selection's end), in UTF-16 units like Accessibility counts.
    public var caret: Int

    public init(field: Int, value: String, caret: Int) {
        self.field = field
        self.value = value
        self.caret = caret
    }
}

/// Reads the focused text field, to see what the user does to the words Milo pasted (ADR 21).
public protocol FocusedTextReader: AnyObject {
    /// nil when no plain text field is focused, or Milo mustn't read it: a password field, a password app,
    /// Milo himself, a field whose value isn't readable or is too long. `done` runs on the main queue.
    func read(_ done: @escaping (FocusedText?) -> Void)
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
    /// The devices the user lent ("mouse", "keyboard"). An action falls back to the real pointer or keyboard
    /// only for a device in this set; otherwise it fails with `HandsFailure.borrow` and touches nothing.
    var borrowed: Set<String> { get set }
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
    /// Bring that window of `pid` to the front, so the user sees Milo work in it.
    func bringForward(pid: Int32, frame: CGRect)
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
    public func bringForward(pid: Int32, frame: CGRect) {}
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

/// A macOS permission the setup window walks through.
public enum Permission: String, CaseIterable, Sendable {
    case microphone, accessibility, screenRecording, calendars, reminders, automation
}

public enum PermissionState: Equatable, Sendable {
    case granted
    /// macOS hasn't asked yet; asking shows its own dialog.
    case notAsked
    case denied
    /// macOS can't say right now, e.g. Mail isn't open to check Automation.
    case unknown
}

/// Reads and asks for permissions. Every call is cheap enough to poll once a second.
public protocol PermissionSource: AnyObject {
    func state(of permission: Permission) -> PermissionState
    /// Puts Milo in the permission's list in System Settings, so he is there to switch on. Shows macOS's own
    /// question where there is one and it wasn't asked yet.
    func register(_ permission: Permission)
    /// Opens the page in System Settings where the user switches Milo on.
    func openSettings(_ permission: Permission)
    /// Forgets Milo's own entry for the permission (`tccutil reset`), e.g. one that shows as on after a rebuild
    /// but no longer counts. Only Milo's bundle id, never another app's.
    func reset(_ permission: Permission)
}

/// Records a meeting in two tracks, "me" (the microphone) and "them" (the call's audio), as 30 s WAV chunks
/// (see ChunkWriter). Callbacks on the main queue.
public protocol MeetingRecorder: AnyObject {
    /// A chunk of `track` is complete and on disk.
    var onChunk: ((_ track: String, _ chunk: ChunkWriter.Finished) -> Void)? { get set }
    /// The tracks being recorded changed. `error` says in plain words why one is missing, "" if none is.
    var onTracks: ((_ tracks: [String], _ error: String) -> Void)? { get set }
    /// What is recorded right now.
    var tracks: [String] { get }
    /// Paused: both tracks go on as silence, so the times stay right and nothing said is kept.
    var paused: Bool { get set }
    func start(dir: URL)
    /// Stops, writes and reports the last chunks, then calls `done`.
    func stop(done: @escaping () -> Void)
}

/// What a call looks like from outside: who uses the microphone, and a browser's window titles.
public protocol CallSignals: AnyObject {
    func micClients() -> [MicClient]
    /// Titles of the windows of the running app with this bundle id, frontmost first.
    func windowTitles(bundle: String) -> [String]
}
