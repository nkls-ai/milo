import Foundation

/// What Milo needs the system's permission for (ADR 25). The brain names the need; the app knows what it is
/// called on this system, how it is asked for and where it is switched on.
public enum AccessNeed: String, Equatable, Sendable {
    /// Control one app with scripts (Excel, Mail, Notes): macOS's Automation, one switch per app.
    case control
    /// Read and work other apps' windows: Accessibility.
    case ui
    /// See the screen's pixels: Screen Recording.
    case screen
    /// Read the address book, to find who a message or a call is for (ADR 39): Contacts, asked once in a dialog.
    case contacts
}

public enum AccessState: String, Equatable, Sendable {
    case yes, no
    /// Not decided: the system asks the user the first time Milo tries.
    case ask
    /// Can't tell, e.g. the app isn't installed.
    case unknown
}

/// An app Milo controls: its name, and its bundle id once known.
public struct AccessApp: Equatable, Hashable, Sendable, Codable {
    public var name: String
    public var bundle: String

    public init(name: String, bundle: String = "") {
        self.name = name
        self.bundle = bundle
    }

    public var label: String { name.isEmpty ? bundle : name }
}

/// The system's answer, with the words Milo uses about it.
public struct AccessAnswer: Equatable, Sendable {
    public var state: AccessState
    public var app: AccessApp?
    /// The system's name ("macOS"), the switch's name ("Accessibility") and the yes button in its question.
    public var system: String
    public var label: String
    public var button: String

    public init(_ state: AccessState, app: AccessApp? = nil, system: String = "", label: String = "", button: String = "") {
        self.state = state
        self.app = app
        self.system = system
        self.label = label
        self.button = button
    }

    var json: JSONValue {
        var fields: [String: JSONValue] = ["access": .string(state.rawValue)]
        if let app {
            fields["app"] = .string(app.name)
            fields["bundle"] = .string(app.bundle)
        }
        if !system.isEmpty { fields["system"] = .string(system) }
        if !label.isEmpty { fields["label"] = .string(label) }
        if !button.isEmpty { fields["button"] = .string(button) }
        return .object(fields)
    }
}

/// The note the brain sends about a permission for work in progress (`access`). "ask": the system is about to ask.
/// "no": it said no; the bubble gets Fix it.
public struct AccessNote: Equatable, Sendable {
    public var need: AccessNeed
    public var state: AccessState
    public var text: String
    public var app: AccessApp?

    public init(need: AccessNeed, state: AccessState, text: String, app: AccessApp? = nil) {
        self.need = need
        self.state = state
        self.text = text
        self.app = app
    }
}

/// What the system lets Milo do. `check` and `request` may block (for `control`, until the app has started, and
/// `request` until the user answers the system's question), so they are called off the main thread.
public protocol AccessSource: AnyObject {
    /// The answer without asking anyone. With `launch`, an app that isn't running is started out of sight first,
    /// since the system can only tell for a running one; the script that follows would start it anyway.
    func check(_ need: AccessNeed, app: AccessApp?, launch: Bool) -> AccessAnswer
    /// Has the system ask the user now, if it hasn't yet, and returns their answer.
    func request(_ need: AccessNeed, app: AccessApp?) -> AccessAnswer
    /// The folders `app` can write without the system stopping it to ask the user. nil: anywhere (not sandboxed).
    func places(for app: AccessApp) -> [String]?
    /// Opens the system's switch for the need: for `control`, the list of apps Milo may control.
    func openSettings(_ need: AccessNeed, app: AccessApp?)
}
