import Foundation

/// How an action reaches an app. See docs/adr/0011-background-delivery.md for what works where.
///
/// Milo works in the background first: Accessibility actions, then events posted to the app's own process.
/// Neither moves the user's pointer or takes their keyboard. Only when neither can do it does he use the real
/// mouse or keyboard, and only after the user agreed to lend them (`borrowed`).
public enum Delivery {
    /// The kinds of app that behave differently.
    public enum Family: String, Sendable {
        /// AppKit and SwiftUI apps: TextEdit, Mail, Numbers, Finder.
        case cocoa
        /// Chrome, Brave, Edge and Electron apps. Their web content reads through Accessibility only once asked
        /// to (AXManualAccessibility), ignores setting the selected text, and coerces a posted right-click to a
        /// left one.
        case chromium
        /// Excel, Word, PowerPoint, Outlook: their documents ignore events posted to the process.
        case office
    }

    public enum Action: Equatable, Sendable {
        case click(right: Bool, count: Int)
        case type
        /// `chord`: with cmd, ctrl or option, which needs the app's window to be key.
        case key(chord: Bool)
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

        public init(pressable: Bool = false, textual: Bool = false, menu: Bool = false, scrollBar: Bool = false) {
            self.pressable = pressable
            self.textual = textual
            self.menu = menu
            self.scrollBar = scrollBar
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
        /// Mouse events posted to the app's process, stamped with its window, after making that window key.
        case processClick
        /// Key events posted to the app's process.
        case processKeys
        case processScroll
        /// The user's own pointer or keyboard, borrowed.
        case real
    }

    /// What has to be lent when no background step can do it.
    public enum Need: String, Sendable {
        case mouse, keyboard
    }

    /// The steps to try for `action`, in order. The last one is `.real` only when the user lent the mouse or
    /// keyboard; without it the plan may come back empty, which means asking first (`need(for:)`).
    /// `skyLight`: the window can be made key without raising it, which posted key chords and clicks into
    /// Chromium need.
    public static func plan(_ action: Action, traits: Traits, family: Family, skyLight: Bool,
                            borrowed: Bool) -> [Step] {
        var steps: [Step] = []
        let posts = family != .office
        switch action {
        case let .click(right, count):
            if right {
                if traits.menu { steps.append(.axShowMenu) }
                // Chromium turns a posted right-click into a left one.
                if posts && family != .chromium && count == 1 { steps.append(.processClick) }
            } else if count == 1 {
                if traits.pressable { steps.append(.axPress) }
                if traits.textual { steps.append(.axFocus) }
                if posts && (family != .chromium || skyLight) { steps.append(.processClick) }
            } else if posts && (family != .chromium || skyLight) {
                steps.append(.processClick)
            }
        case .type:
            // Chromium says yes to AXSelectedText and does nothing, so it goes straight to keys.
            if family != .chromium { steps.append(.axInsert) }
            if posts { steps.append(.processKeys) }
        case let .key(chord):
            if posts && (!chord || skyLight) { steps.append(.processKeys) }
        case .scroll:
            if traits.scrollBar { steps.append(.axScrollBar) }
            if posts { steps.append(.processScroll) }
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

    /// Whether a failed step may hand over to the next one. A posted click or key can land without anything
    /// Milo can read changing, so after it nothing else is tried: a second try could click or type twice.
    public static func mayFallThrough(after step: Step, verified: Bool?) -> Bool {
        switch step {
        case .axPress, .axFocus, .axShowMenu, .axInsert, .axScrollBar: true
        // Keys whose effect could be read and didn't show may go on to the borrowed keyboard.
        case .processKeys: verified == false
        case .processClick, .processScroll, .real: false
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
