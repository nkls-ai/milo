import AppKit
import ApplicationServices

/// FieldProbe through Accessibility (ADR 0033). Reads on a queue of its own with a short timeout, so a busy or hung
/// app never stalls Milo. A password field's value is never read; for the others only what Undo needs is.
public final class AXFieldProbe: FieldProbe {
    private let queue = DispatchQueue(label: "milo.field-probe", qos: .userInitiated)

    public init() {}

    public func focused(_ done: @escaping (FocusedField?) -> Void) {
        queue.async {
            let field = Self.element().map { Self.describe($0) }
            DispatchQueue.main.async { done(field) }
        }
    }

    public func remove(_ text: String, from field: Int, _ done: @escaping (Bool) -> Void) {
        queue.async {
            let removed = Self.removeNow(text, from: field)
            DispatchQueue.main.async { done(removed) }
        }
    }

    static let textRoles: Set<String> = ["AXTextArea", "AXTextField", "AXComboBox", "AXSearchField"]

    static func element() -> AXUIElement? {
        guard AXIsProcessTrusted() else { return nil }
        let system = AXUIElementCreateSystemWide()
        AXUIElementSetMessagingTimeout(system, 0.25)
        guard let element: AXUIElement = AX.attribute(system, kAXFocusedUIElementAttribute) else { return nil }
        AXUIElementSetMessagingTimeout(element, 0.25)
        return element
    }

    static func describe(_ element: AXUIElement) -> FocusedField {
        let pid = AX.pid(element)
        let app = NSRunningApplication(processIdentifier: pid)
        let role = AX.role(element)
        let label = [kAXTitleAttribute, kAXDescriptionAttribute, kAXPlaceholderValueAttribute, kAXHelpAttribute,
                     kAXRoleDescriptionAttribute]
            .compactMap { AX.string(element, $0) }.joined(separator: " ").lowercased()
        var settable: DarwinBoolean = false
        let canSet = AXUIElementIsAttributeSettable(element, kAXValueAttribute as CFString, &settable) == .success
            && settable.boolValue
        // Web content that takes typing (a mail body, a chat box) says so through its editable ancestor.
        let webEditable = (AX.attribute(element, "AXEditableAncestor") as AXUIElement?) != nil
        return FocusedField(pid: pid, app: app?.localizedName ?? "", bundle: app?.bundleIdentifier ?? "",
                            field: id(element, pid), role: role, label: label,
                            editable: textRoles.contains(role) || canSet || webEditable, settable: canSet || webEditable,
                            secure: AX.isSecure(element) || AX.isSecret(app), milo: pid == getpid())
    }

    /// Equal elements hash alike (CFEqual), so the same field gives the same number on every read.
    static func id(_ element: AXUIElement, _ pid: pid_t) -> Int {
        Int(bitPattern: UInt(CFHash(element))) &* 31 &+ Int(pid)
    }

    /// Select exactly `text` right before the caret and delete it. Gives up when the field changed: another field,
    /// a selection, other text there, or a value Accessibility doesn't show.
    static func removeNow(_ text: String, from field: Int) -> Bool {
        guard let element = element() else { return false }
        let pid = AX.pid(element)
        guard id(element, pid) == field, !AX.isSecure(element),
              let value: String = AX.attribute(element, kAXValueAttribute),
              let range = selection(element), range.length == 0 else { return false }
        let wanted = Array(normalized(text).utf16)
        let caret = range.location
        let units = Array(normalized(value).utf16)
        guard caret <= units.count, caret >= wanted.count,
              Array(units[(caret - wanted.count)..<caret]) == wanted else { return false }
        var span = CFRange(location: caret - wanted.count, length: wanted.count)
        guard let spanValue = AXValueCreate(.cfRange, &span),
              AXUIElementSetAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, spanValue) == .success,
              let selected = selection(element), selected.location == span.location, selected.length == span.length
        else { return false }
        if AXUIElementSetAttributeValue(element, kAXSelectedTextAttribute as CFString, "" as CFString) != .success {
            pressDelete()
        }
        let after: String? = AX.attribute(element, kAXValueAttribute)
        return after.map { $0.utf16.count == units.count - wanted.count } ?? false
    }

    private static func selection(_ element: AXUIElement) -> CFRange? {
        guard let value: AXValue = AX.attribute(element, kAXSelectedTextRangeAttribute) else { return nil }
        var range = CFRange()
        return AXValueGetValue(value, .cfRange, &range) ? range : nil
    }

    /// Apps store a pasted line break as "\n" or "\r"; both are one unit, so positions stay the same.
    private static func normalized(_ text: String) -> String {
        text.replacingOccurrences(of: "\r", with: "\n")
    }

    /// Where setting the selected text isn't taken (much web content), the selection goes with a Delete key.
    private static func pressDelete() {
        let source = CGEventSource(stateID: .combinedSessionState)
        for down in [true, false] {
            let event = CGEvent(keyboardEventSource: source, virtualKey: 51, keyDown: down)
            event?.setIntegerValueField(.eventSourceUserData, value: PasteboardInserter.eventMarker)
            event?.post(tap: .cghidEventTap)
        }
        usleep(50_000)  // let the app take the key before the value is read back
    }
}
