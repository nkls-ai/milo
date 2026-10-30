import AppKit
import ApplicationServices

/// FocusedTextReader through Accessibility. Reads on a queue of its own with a short timeout, so a busy or hung
/// app never stalls Milo. Never reads password fields, password apps or Milo's own windows.
public final class AXFocusedText: FocusedTextReader {
    /// Longer fields (a whole book in a text editor) aren't read at all.
    public static let maxLength = 100_000

    private let queue = DispatchQueue(label: "milo.focused-text", qos: .utility)

    public init() {}

    public func read(_ done: @escaping (FocusedText?) -> Void) {
        queue.async {
            let text = Self.readNow()
            DispatchQueue.main.async { done(text) }
        }
    }

    static func readNow() -> FocusedText? {
        guard AXIsProcessTrusted() else { return nil }
        let system = AXUIElementCreateSystemWide()
        AXUIElementSetMessagingTimeout(system, 0.25)
        guard let element: AXUIElement = AX.attribute(system, kAXFocusedUIElementAttribute) else { return nil }
        AXUIElementSetMessagingTimeout(element, 0.25)
        let pid = AX.pid(element)
        guard pid != getpid(), !AX.isSecret(NSRunningApplication(processIdentifier: pid)), !AX.isSecure(element)
        else { return nil }
        // Asked first, so a huge document isn't copied over just to be dropped.
        if let count: Int = AX.attribute(element, kAXNumberOfCharactersAttribute), count > maxLength { return nil }
        guard let value: String = AX.attribute(element, kAXValueAttribute), value.utf16.count <= maxLength,
              let selection: AXValue = AX.attribute(element, kAXSelectedTextRangeAttribute) else { return nil }
        var range = CFRange()
        guard AXValueGetValue(selection, .cfRange, &range) else { return nil }
        // Equal elements hash alike (CFEqual), so the same field gives the same number on every read.
        let field = Int(bitPattern: UInt(CFHash(element))) &* 31 &+ Int(pid)
        return FocusedText(field: field, value: value, caret: range.location + range.length)
    }
}

/// WordList over the Mac's spell checker, in the languages the user set in System Settings: a word counts if
/// any of them knows it.
public final class SpellCheckWords: WordList {
    public init() {}

    public func isWord(_ word: String) -> Bool {
        let checker = NSSpellChecker.shared
        let languages = Array(checker.userPreferredLanguages.prefix(3))
        return (languages.isEmpty ? [checker.language()] : languages).contains { language in
            checker.checkSpelling(of: word, startingAt: 0, language: language, wrap: false,
                                  inSpellDocumentWithTag: 0, wordCount: nil).location == NSNotFound
        }
    }
}
