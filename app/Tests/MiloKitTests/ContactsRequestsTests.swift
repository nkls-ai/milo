import Foundation
import Testing
@testable import MiloKit

/// The brain's `contacts.find` (ADR 39): who "Anna" or "Mum" is, for a message or a call. Which one the user meant
/// is the brain's choice; the app finds the candidates.
@Suite struct ContactsRequestsTests {
    final class Book: ContactBook {
        var cards: [ContactCard]
        var mine: ContactCard?
        var refused = false

        init(_ cards: [ContactCard], me: ContactCard? = nil) {
            self.cards = cards
            mine = me
        }

        func everyone() throws -> [ContactCard] {
            if refused { throw ContactBookError(text: "Milo isn't allowed to look in your contacts.") }
            return cards
        }

        func me() -> ContactCard? { mine }
    }

    static let anna = ContactCard(name: "Anna Berg", phones: [.init("mobile", "+49 170 1234567")])
    static let annabel = ContactCard(name: "Annabel Ross", nickname: "Bel")
    static let zoe = ContactCard(name: "Zoë Kim", emails: [.init("home", "zoe@example.com")])
    static let jane = ContactCard(name: "Jane Doe", phones: [.init("iPhone", "+49 160 2222222")])
    static let me = ContactCard(name: "Sam Doe", relations: [.init("mother", "Jane Doe"), .init("Mum", "Jane Doe")])

    private func find(_ book: Book, _ args: [String: JSONValue]) -> AppOutcome? {
        let requests = ContactsRequests(book: book, queue: DispatchQueue(label: "test"), main: { $0() })
        let done = DispatchSemaphore(value: 0)
        var outcome: AppOutcome?
        requests.handle(op: "contacts.find", args: .object(args)) {
            outcome = $0
            done.signal()
        }
        done.wait()
        return outcome
    }

    private func names(_ outcome: AppOutcome?) -> [String] {
        guard case let .success(.array(found)) = outcome else { return [] }
        return found.compactMap { $0["name"]?.string }
    }

    @Test func aFirstNameFindsEveryoneWhoseNameStartsLikeIt() {
        let book = Book([Self.anna, Self.annabel, Self.jane])
        #expect(names(find(book, ["name": .string("anna")])) == ["Anna Berg", "Annabel Ross"])
        #expect(names(find(book, ["name": .string("Anna Ber")])) == ["Anna Berg"])
        #expect(names(find(book, ["name": .string("bel")])) == ["Annabel Ross"], "the nickname counts")
    }

    @Test func accentsAndCaseDontMatter() {
        #expect(names(find(Book([Self.zoe]), ["name": .string("zoe")])) == ["Zoë Kim"])
    }

    @Test func mumIsWhomTheUsersOwnCardNamesAsMother() {
        let book = Book([Self.anna, Self.jane], me: Self.me)
        guard case let .success(.array(found)) = find(book, ["name": .string("Mum"), "relation": .string("mother")])
        else { Issue.record("no answer"); return }
        #expect(found.count == 1, "under two labels, one person")
        #expect(found.first?["name"]?.string == "Jane Doe")
        #expect(found.first?["relation"]?.string == "mother")
        #expect(found.first?["phones"]?.array?.first?["value"]?.string == "+49 160 2222222")
    }

    @Test func aWifeMayBeKeptAsSpouse() {
        #expect(ContactsRequests.labels(for: "wife").contains("spouse"))
        #expect(ContactsRequests.fold("_$!<Mother>!$_") == "mother")
    }

    @Test func aRefusalComesBackInPlainWords() {
        let book = Book([Self.anna])
        book.refused = true
        #expect(find(book, ["name": .string("Anna")]) == .failure("Milo isn't allowed to look in your contacts."))
    }

    @Test func otherOpsGoToTheNextConnection() {
        final class Next: AppConnections {
            var ops: [String] = []
            func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
                ops.append(op)
                reply(.success(.null))
            }
        }
        let next = Next()
        ContactsRequests(book: Book([]), next: next).handle(op: "calendar.events", args: .object([:])) { _ in }
        #expect(next.ops == ["calendar.events"])
    }
}
