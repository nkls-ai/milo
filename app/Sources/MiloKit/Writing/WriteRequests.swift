import Foundation

/// The brain's `text.*` ops (ADR 0033): text Milo wrote goes where the user was when they started talking.
///
/// - `text.write` {text, paste}: {pasted, app, field} or {pasted: false, why, app}. With `paste` false the brain only
///   wants the text kept to copy (it came after outside text the user didn't ask about). `why` is "here", "moved",
///   "no_field", "secure", "terminal", "held" or "blocked" (no Accessibility, so a paste would vanish).
/// - `text.unwrite` {field, text}: {removed: true}, or a failure in plain words that names the app's own Undo.
///
/// The paste is dictation's: `TextInserter` puts it on the clipboard, presses ⌘V and puts the user's clipboard back.
/// Text that doesn't go in is offered to copy under the next bubble (`onKept`).
public final class WriteRequests: AppConnections {
    private let probe: FieldProbe
    private let inserter: TextInserter
    private let trusted: () -> Bool
    private let next: AppConnections?
    /// The focus when the talk key last went down: the only place written text may go.
    private(set) var keyDown: FocusedField?
    /// The apps Milo pasted into, by field, for the Undo words.
    private var apps: [Int: String] = [:]
    /// Called with the text after it went in, on the main queue.
    public var onPasted: ((String) -> Void)?
    /// Called with text that stays in Milo's window to copy, on the main queue.
    public var onKept: ((String) -> Void)?

    public init(probe: FieldProbe, inserter: TextInserter, trusted: @escaping () -> Bool, next: AppConnections? = nil) {
        self.probe = probe
        self.inserter = inserter
        self.trusted = trusted
        self.next = next
    }

    /// The talk key went down: remember where the user is, off the main queue so the key isn't held up.
    public func capture() {
        keyDown = nil
        probe.focused { [weak self] in self?.keyDown = $0 }
    }

    public func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
        switch op {
        case "text.write": write(args, reply)
        case "text.unwrite": unwrite(args, reply)
        default:
            guard let next else { return reply(.failure("Milo's app doesn't know how to do \(op).")) }
            next.handle(op: op, args: args, reply: reply)
        }
    }

    private func write(_ args: JSONValue, _ reply: @escaping (AppOutcome) -> Void) {
        let text = args["text"]?.string ?? ""
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return reply(.failure("There was no text to paste."))
        }
        guard args["paste"]?.bool ?? true else { return keep(text, why: "held", app: "", reply) }
        // Without Accessibility macOS drops Milo's ⌘V without a word.
        guard trusted() else { return keep(text, why: "blocked", app: "", reply) }
        let keyDown = keyDown
        probe.focused { [weak self] now in
            guard let self else { return }
            switch PasteTarget.verdict(keyDown: keyDown, now: now) {
            case .paste:
                guard let now else { return }
                inserter.insert(text)
                apps[now.field] = now.app
                onPasted?(text)
                reply(.success(.object(["pasted": .bool(true), "app": .string(now.app),
                                        "field": .string(Self.id(now.field))])))
            case let .keep(why):
                keep(text, why: why, app: now?.app ?? "", reply)
            }
        }
    }

    private func keep(_ text: String, why: String, app: String, _ reply: (AppOutcome) -> Void) {
        onKept?(text)
        reply(.success(.object(["pasted": .bool(false), "why": .string(why), "app": .string(app)])))
    }

    private func unwrite(_ args: JSONValue, _ reply: @escaping (AppOutcome) -> Void) {
        let text = args["text"]?.string ?? ""
        guard let field = Self.field(args["field"]?.string ?? ""), !text.isEmpty else {
            return reply(.failure(Self.undoByHand(nil)))
        }
        let app = apps[field]
        probe.remove(text, from: field) { removed in
            reply(removed ? .success(.object(["removed": .bool(true)])) : .failure(Self.undoByHand(app)))
        }
    }

    /// The field's opaque id on the wire: the brain only echoes it back.
    static func id(_ field: Int) -> String { "f-\(field)" }

    static func field(_ id: String) -> Int? {
        id.hasPrefix("f-") ? Int(id.dropFirst(2)) : nil
    }

    /// When Milo can't find his text where it went in any more, the app's own Undo still can.
    static func undoByHand(_ app: String?) -> String {
        let place = app.map { $0.isEmpty ? "there" : "in \($0)" } ?? "there"
        return "The text there changed since, so I left it. Press ⌘Z \(place) to take it back."
    }
}
