import Foundation

/// How an action reaches an app. See docs/adr/0012-background-delivery.md for what works where.
///
/// Milo works in the background first, through Accessibility actions: pressing a button, focusing a field,
/// putting the caret, inserting text, setting a scroll bar. None of them moves the user's pointer or takes
/// their keyboard. When none of them can do it, he uses the real mouse or keyboard, and only after the user
/// agreed to lend them (`borrowed`).
public enum Delivery {
    /// The kinds of app that behave differently.
    public enum Family: String, Sendable {
        /// AppKit and SwiftUI apps: TextEdit, Mail, Numbers, Finder.
        case cocoa
        /// Chrome, Brave, Edge and Electron apps. Their web content reads through Accessibility only once asked
        /// to, and they answer yes to setting the selected text without doing it.
        case chromium
        /// Excel, Word, PowerPoint, Outlook: their ribbons press through Accessibility, their documents don't.
        case office
    }

    public enum Action: Equatable, Sendable {
        case click(right: Bool, count: Int)
        case type
        case key
        case scroll
    }

    /// What the element under the action offers, read through Accessibility.
    public struct Traits: Equatable, Sendable {
        /// It has AXPress (a button, checkbox, link, menu item, tab).
        public var pressable = false
        /// A text field or text area: a click focuses it and puts the caret there.
        public var textual = false
        /// It offers AXShowMenu, so a right-click can open its menu.
        public var menu = false
        /// A scroll bar Milo can set lies under the point.
        public var scrollBar = false
        /// Its selected text can be set, so typing can insert there.
        public var insertable = false

        public init(pressable: Bool = false, textual: Bool = false, menu: Bool = false, scrollBar: Bool = false,
                    insertable: Bool = false) {
            self.pressable = pressable
            self.textual = textual
            self.menu = menu
            self.scrollBar = scrollBar
            self.insertable = insertable
        }
    }

    /// One way to try, in order.
    public enum Step: Equatable, Sendable {
        case axPress
        /// Focus the text element and put the caret under the point.
        case axFocus
        case axShowMenu
        /// Insert the text at the caret through AXSelectedText, read back to check.
        case axInsert
        case axScrollBar
        /// The user's own pointer or keyboard, lent.
        case real
    }

    /// What has to be lent when no background step can do it.
    public enum Need: String, Sendable {
        case mouse, keyboard
    }

    /// The steps to try for `action`, in order. The last one is `.real` only when the user lent the mouse or
    /// keyboard; without it the plan may come back empty, which means asking first (`need(for:)`).
    public static func plan(_ action: Action, traits: Traits, family: Family, borrowed: Bool) -> [Step] {
        var steps: [Step] = []
        switch action {
        case let .click(right, count):
            if right {
                if traits.menu && count == 1 { steps.append(.axShowMenu) }
            } else if count == 1 {
                if traits.pressable { steps.append(.axPress) }
                if traits.textual { steps.append(.axFocus) }
            }
        case .type:
            // Chromium says yes to AXSelectedText and does nothing; the read-back would catch it, but slowly.
            if traits.insertable && family != .chromium { steps.append(.axInsert) }
        case .key:
            break
        case .scroll:
            if traits.scrollBar { steps.append(.axScrollBar) }
        }
        if borrowed { steps.append(.real) }
        return steps
    }

    /// What the user is asked to lend for `action`.
    public static func need(for action: Action) -> Need {
        switch action {
        case .click, .scroll: .mouse
        case .type, .key: .keyboard
        }
    }

    /// The family of an app from its bundle id and whether it ships Electron or Chromium inside.
    public static func family(bundleID: String?, embedsChromium: Bool) -> Family {
        let id = bundleID?.lowercased() ?? ""
        if officeIDs.contains(id) { return .office }
        if embedsChromium || chromiumIDs.contains(where: id.hasPrefix) { return .chromium }
        return .cocoa
    }

    static let officeIDs: Set<String> = ["com.microsoft.excel", "com.microsoft.word", "com.microsoft.powerpoint",
                                         "com.microsoft.outlook", "com.microsoft.onenote.mac"]
    static let chromiumIDs = ["com.google.chrome", "com.brave.browser", "com.microsoft.edgemac", "com.vivaldi.vivaldi",
                              "com.operasoftware.opera", "company.thebrowser.browser", "org.chromium.chromium"]
}
