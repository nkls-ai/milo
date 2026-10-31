import Foundation

/// One card of the address book, as the brain needs it: the name, the nickname, numbers and addresses with their
/// labels in plain words ("mobile", "iPhone", "home"), and, on the user's own card, whom it names as family
/// (label "mother", value "Jane Doe").
public struct ContactCard: Equatable, Sendable {
    public struct Labeled: Equatable, Sendable {
        public var label: String
        public var value: String

        public init(_ label: String, _ value: String) {
            self.label = label
            self.value = value
        }
    }

    public var name: String
    public var nickname: String
    public var phones: [Labeled]
    public var emails: [Labeled]
    public var relations: [Labeled]

    public init(name: String, nickname: String = "", phones: [Labeled] = [], emails: [Labeled] = [],
                relations: [Labeled] = []) {
        self.name = name
        self.nickname = nickname
        self.phones = phones
        self.emails = emails
        self.relations = relations
    }
}

/// The user's address book, read only. Both calls block and may ask the system for access the first time; they
/// run off the main queue.
public protocol ContactBook: AnyObject {
    /// Everyone in it. Throws with plain words when Milo may not read it.
    func everyone() throws -> [ContactCard]
    /// The user's own card, nil when there is none.
    func me() -> ContactCard?
}

/// The brain's `contacts.*` op (ADR 39), in front of the other app connections.
///
/// - `contacts.find` {name, relation?}: [{name, nickname?, relation?, phones: [{label, value}], emails: [...]}],
///   everyone whose name, a word of it or their nickname starts like each word of `name`, case and accents aside.
///   With `relation` ("mother", "brother", "wife"), also whom the user's own card names with it, or with `name`
///   itself as the label ("Mum"), marked with the relation.
///
/// Which of them the user meant is the brain's choice; this side only finds them.
public final class ContactsRequests: AppConnections {
    private let book: ContactBook
    private let next: AppConnections?
    private let queue: DispatchQueue
    private let main: (@escaping () -> Void) -> Void
    static let limit = 20

    public init(book: ContactBook, next: AppConnections? = nil,
                queue: DispatchQueue = DispatchQueue(label: "milo.contacts", qos: .userInitiated),
                main: @escaping (@escaping () -> Void) -> Void = { DispatchQueue.main.async(execute: $0) }) {
        self.book = book
        self.next = next
        self.queue = queue
        self.main = main
    }

    public func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
        guard op.hasPrefix("contacts.") else {
            guard let next else { return reply(.failure("Milo's app doesn't know how to do \(op).")) }
            return next.handle(op: op, args: args, reply: reply)
        }
        guard op == "contacts.find" else { return reply(.failure("Milo's app doesn't know how to do \(op).")) }
        let name = args["name"]?.string ?? "", relation = args["relation"]?.string ?? ""
        guard !name.trimmingCharacters(in: .whitespaces).isEmpty || !relation.isEmpty else {
            return reply(.failure("Say whom to look for."))
        }
        queue.async { [self] in
            let outcome: AppOutcome
            do {
                outcome = .success(.array(try find(name, relation: relation)))
            } catch {
                outcome = .failure(error.localizedDescription)
            }
            main { reply(outcome) }
        }
    }

    func find(_ name: String, relation: String) throws -> [JSONValue] {
        let everyone = try book.everyone()
        let want = Self.fold(name).split(separator: " ").map(String.init)
        var found: [(card: ContactCard, relation: String)] = []
        if !relation.isEmpty, let me = book.me() {
            let labels = Self.labels(for: relation).union([Self.fold(name)])
            for named in me.relations where labels.contains(Self.fold(named.label)) {
                let who = Self.fold(named.value)
                for card in everyone where Self.fold(card.name) == who && !found.contains(where: { $0.card == card }) {
                    found.append((card, relation))
                }
            }
        }
        for card in everyone where !want.isEmpty && !found.contains(where: { $0.card == card }) {
            let words = Self.fold("\(card.name) \(card.nickname)").split(separator: " ")
            if want.allSatisfy({ w in words.contains { $0.hasPrefix(w) } }) { found.append((card, "")) }
        }
        return found.prefix(Self.limit).map { Self.json($0.card, relation: $0.relation) }
    }

    /// The labels a card may keep a relation under: a wife may be under "spouse" or "partner".
    static func labels(for relation: String) -> Set<String> {
        let relation = fold(relation)
        let spouses: Set<String> = ["wife", "husband", "spouse", "partner"]
        return spouses.contains(relation) ? spouses : [relation]
    }

    /// Lower case without accents or the address book's label markers ("_$!<Mother>!$_" is "mother").
    static func fold(_ text: String) -> String {
        text.replacingOccurrences(of: "_$!<", with: "").replacingOccurrences(of: ">!$_", with: "")
            .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }

    static func json(_ card: ContactCard, relation: String) -> JSONValue {
        let labeled = { (items: [ContactCard.Labeled]) in
            JSONValue.array(items.map { .object(["label": .string($0.label), "value": .string($0.value)]) })
        }
        var fields: [String: JSONValue] = ["name": .string(card.name), "phones": labeled(card.phones),
                                           "emails": labeled(card.emails)]
        if !card.nickname.isEmpty { fields["nickname"] = .string(card.nickname) }
        if !relation.isEmpty { fields["relation"] = .string(relation) }
        return .object(fields)
    }
}
