import Contacts
import Foundation

/// The address book through CNContactStore (ADR 39), read only. The brain says before the first use that macOS
/// will ask (ADR 25); if it still hasn't, the first read asks and waits for the answer.
public final class SystemContactBook: ContactBook {
    private lazy var store = CNContactStore()

    public init() {}

    private static let keys: [CNKeyDescriptor] = [
        CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
        CNContactNicknameKey as CNKeyDescriptor, CNContactOrganizationNameKey as CNKeyDescriptor,
        CNContactPhoneNumbersKey as CNKeyDescriptor, CNContactEmailAddressesKey as CNKeyDescriptor,
        CNContactRelationsKey as CNKeyDescriptor,
    ]

    static let denied = "Milo isn't allowed to look in your contacts. Turn it on in System Settings › Privacy & Security › Contacts."

    public func everyone() throws -> [ContactCard] {
        try allowed()
        var cards: [ContactCard] = []
        let request = CNContactFetchRequest(keysToFetch: Self.keys)
        request.unifyResults = true
        do {
            try store.enumerateContacts(with: request) { contact, _ in
                if let card = Self.card(contact) { cards.append(card) }
            }
        } catch {
            throw ContactBookError(text: "I couldn't read your contacts.")
        }
        return cards
    }

    public func me() -> ContactCard? {
        guard (try? allowed()) != nil else { return nil }
        return (try? store.unifiedMeContactWithKeys(toFetch: Self.keys)).flatMap(Self.card)
    }

    private func allowed() throws {
        switch CNContactStore.authorizationStatus(for: .contacts) {
        case .authorized: return
        case .notDetermined:
            var granted = false
            let answered = DispatchSemaphore(value: 0)
            store.requestAccess(for: .contacts) { yes, _ in
                granted = yes
                answered.signal()
            }
            answered.wait()
            if !granted { throw ContactBookError(text: Self.denied) }
        case .denied, .restricted: throw ContactBookError(text: Self.denied)
        @unknown default: return
        }
    }

    private static func card(_ contact: CNContact) -> ContactCard? {
        let name = CNContactFormatter.string(from: contact, style: .fullName) ?? contact.organizationName
        guard !name.isEmpty else { return nil }
        return ContactCard(
            name: name, nickname: contact.nickname,
            phones: contact.phoneNumbers.map { .init(label($0.label), $0.value.stringValue) },
            emails: contact.emailAddresses.map { .init(label($0.label), $0.value as String) },
            relations: contact.contactRelations.map { .init(label($0.label), $0.value.name) })
    }

    /// "_$!<Mobile>!$_" as "Mobile"; a label the user typed as it is.
    private static func label(_ raw: String?) -> String {
        (raw ?? "").replacingOccurrences(of: "_$!<", with: "").replacingOccurrences(of: ">!$_", with: "")
    }
}

struct ContactBookError: LocalizedError {
    let text: String
    var errorDescription: String? { text }
}
