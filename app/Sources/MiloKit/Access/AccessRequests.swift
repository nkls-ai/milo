import Foundation

/// The brain's `access.*` ops (ADR 25), in front of the other app connections (Calendar and Reminders).
///
/// - `access.check` {need, app?, bundle?, launch?}: the system's answer without asking the user.
/// - `access.request` {need, app?, bundle?}: the system asks the user now if it hasn't, and this waits for them.
/// - `access.places` {app, bundle?}: {sandboxed, places}: where the app can save without the system asking.
///
/// The answers are {access: yes|no|ask|unknown, app, bundle, system, label, button}. The words for the user are
/// the brain's; this side only says what the system is called, what it calls the switch and its yes button.
/// While the system's question is up, `onAsking` is told, so the stop-on-touch check doesn't take the click on it
/// for the user taking over.
public final class AccessRequests: AppConnections {
    private let source: AccessSource
    private let apps: ControlledApps
    private let next: AppConnections?
    private let queue: DispatchQueue
    private let main: (@escaping () -> Void) -> Void
    /// True while the system's question is up, false once it is answered. On the main queue.
    public var onAsking: ((Bool) -> Void)?

    public init(source: AccessSource, apps: ControlledApps, next: AppConnections? = nil,
                queue: DispatchQueue = DispatchQueue(label: "milo.access", qos: .userInitiated),
                main: @escaping (@escaping () -> Void) -> Void = { DispatchQueue.main.async(execute: $0) }) {
        self.source = source
        self.apps = apps
        self.next = next
        self.queue = queue
        self.main = main
    }

    public func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
        guard op.hasPrefix("access.") else {
            guard let next else { return reply(.failure("Milo's app doesn't know how to do \(op).")) }
            return next.handle(op: op, args: args, reply: reply)
        }
        let need = AccessNeed(rawValue: args["need"]?.string ?? "")
        let name = args["app"]?.string ?? "", bundle = args["bundle"]?.string ?? ""
        let app = name.isEmpty && bundle.isEmpty ? nil : AccessApp(name: name, bundle: bundle)
        let done: (AppOutcome) -> Void = { [main] outcome in main { reply(outcome) } }
        switch op {
        case "access.check", "access.request":
            guard let need, need != .control || app != nil else {
                return reply(.failure("access needs a need (control, ui or screen) and, for control, an app."))
            }
            let asking = op == "access.request" && need == .control
            if asking { onAsking?(true) }
            queue.async { [self] in
                let answer = asking ? source.request(need, app: app)
                    : source.check(need, app: app, launch: args["launch"]?.bool ?? false)
                main { [self] in
                    if asking { onAsking?(false) }
                    if need == .control { apps.note(answer) }
                }
                done(.success(answer.json))
            }
        case "access.places":
            guard let app else { return reply(.failure("access.places needs an app.")) }
            queue.async { [self] in
                let places = source.places(for: app)
                done(.success(.object(["sandboxed": .bool(places != nil),
                                       "places": .array((places ?? []).map(JSONValue.string))])))
            }
        default:
            reply(.failure("Milo's app doesn't know how to do \(op)."))
        }
    }
}
