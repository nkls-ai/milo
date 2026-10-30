import AppKit
import ApplicationServices

/// Reading other apps through the Accessibility API. Password fields are never read.
enum AX {
    static let systemWide = AXUIElementCreateSystemWide()
    static let notTrusted = "I can't read windows yet. Turn on Accessibility for Milo in System Settings › Privacy & Security › Accessibility."

    static func attribute<T>(_ element: AXUIElement, _ name: String) -> T? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success else { return nil }
        return value as? T
    }

    static func string(_ element: AXUIElement, _ name: String) -> String? {
        guard let text: String = attribute(element, name) else { return nil }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    static func role(_ element: AXUIElement) -> String { string(element, kAXRoleAttribute) ?? "" }

    static func isSecure(_ element: AXUIElement) -> Bool {
        role(element) == "AXSecureTextField" || string(element, kAXSubroleAttribute) == kAXSecureTextFieldSubrole
    }

    static func children(_ element: AXUIElement) -> [AXUIElement] {
        // Lists and tables report only their visible rows here, which keeps a long mailbox cheap.
        if let visible: [AXUIElement] = attribute(element, kAXVisibleChildrenAttribute), !visible.isEmpty { return visible }
        return attribute(element, kAXChildrenAttribute) ?? []
    }

    static func pid(_ element: AXUIElement) -> pid_t {
        var pid: pid_t = 0
        AXUIElementGetPid(element, &pid)
        return pid
    }

    /// The element's frame in global points, origin top-left.
    static func frame(_ element: AXUIElement) -> CGRect? {
        guard let position: AXValue = attribute(element, kAXPositionAttribute),
              let size: AXValue = attribute(element, kAXSizeAttribute) else { return nil }
        var origin = CGPoint.zero, extent = CGSize.zero
        guard AXValueGetValue(position, .cgPoint, &origin), AXValueGetValue(size, .cgSize, &extent) else { return nil }
        return CGRect(origin: origin, size: extent)
    }

    static func application(_ pid: pid_t) -> AXUIElement {
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, 0.5)  // a hung app must not hang Milo
        return app
    }

    static func window(of app: AXUIElement) -> AXUIElement? {
        attribute(app, kAXFocusedWindowAttribute) ?? attribute(app, kAXMainWindowAttribute)
    }

    static func focused() -> AXUIElement? {
        attribute(systemWide, kAXFocusedUIElementAttribute)
    }

    /// The element of another app under `point`. Milo's own windows (the frame, the character) are looked
    /// through, so the safety check sees what the click will really hit. nil if nothing can be named.
    static func element(at point: CGPoint) -> AXUIElement? {
        var element: AXUIElement?
        if AXUIElementCopyElementAtPosition(systemWide, Float(point.x), Float(point.y), &element) == .success,
           let element, pid(element) != getpid() {
            return element
        }
        // Only an ordinary window on top is looked into. A menu or overlay on top could take the click.
        guard let top = windows(at: point).first, top.layer == 0 else { return nil }
        var inner: AXUIElement?
        guard AXUIElementCopyElementAtPosition(application(top.pid), Float(point.x), Float(point.y), &inner) == .success
        else { return nil }
        return inner
    }

    /// The windows of other apps under `point`, front to back, Milo's skipped.
    static func windows(at point: CGPoint) -> [(pid: pid_t, layer: Int)] {
        let info = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] ?? []
        return info.compactMap { window in
            guard let pid = window[kCGWindowOwnerPID as String] as? pid_t, pid != getpid(),
                  let bounds = window[kCGWindowBounds as String] as? NSDictionary,
                  let rect = CGRect(dictionaryRepresentation: bounds), rect.contains(point) else { return nil }
            return (pid, window[kCGWindowLayer as String] as? Int ?? 0)
        }
    }

    /// The apps that could get a click at `point`: every window down to the first ordinary one.
    static func owners(at point: CGPoint) -> [NSRunningApplication] {
        let stack = windows(at: point)
        let reach = stack.firstIndex { $0.layer == 0 }.map { stack.prefix(through: $0) } ?? stack[...]
        return reach.compactMap { NSRunningApplication(processIdentifier: $0.pid) }
    }

    /// Password managers: Milo never reads or looks at them.
    static let secretApps: Set<String> = ["com.apple.keychainaccess", "com.apple.Passwords", "com.1password.1password",
                                          "com.agilebits.onepassword7", "com.bitwarden.desktop", "com.lastpass.LastPass",
                                          "com.dashlane.dashlanephonefinal", "org.keepassxc.keepassxc"]
    static let secretRefused = "That's a password app. Milo never reads or looks at it."

    static func isSecret(_ app: NSRunningApplication?) -> Bool {
        app?.bundleIdentifier.map(secretApps.contains) ?? false
    }

    /// What a person would call it: its title, description or (for fields that aren't secret) its value.
    static func label(_ element: AXUIElement) -> String {
        let secure = isSecure(element)
        let candidates = [string(element, kAXTitleAttribute), string(element, kAXDescriptionAttribute),
                          secure ? nil : (attribute(element, kAXValueAttribute) as String?),
                          string(element, kAXPlaceholderValueAttribute), string(element, kAXHelpAttribute)]
        let text = candidates.compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }.first { !$0.isEmpty } ?? ""
        return clip(text, 80)
    }

    static func roleName(_ element: AXUIElement) -> String {
        if isSecure(element) { return "password field" }
        let role = role(element)
        return roleNames[role] ?? string(element, kAXRoleDescriptionAttribute) ?? role.replacingOccurrences(of: "AX", with: "")
    }

    static let roleNames = [
        "AXButton": "button", "AXCheckBox": "checkbox", "AXRadioButton": "radio button", "AXPopUpButton": "pop-up",
        "AXMenuButton": "menu button", "AXTextField": "text field", "AXTextArea": "text area", "AXComboBox": "combo box",
        "AXLink": "link", "AXMenuItem": "menu item", "AXSlider": "slider", "AXDisclosureTriangle": "disclosure",
        "AXCell": "cell", "AXRow": "row", "AXStaticText": "text", "AXHeading": "heading", "AXTabGroup": "tabs",
        "AXSearchField": "search field", "AXIncrementor": "stepper", "AXImage": "image", "AXWebArea": "web page",
    ]
    static let actionable: Set<String> = [
        "AXButton", "AXCheckBox", "AXRadioButton", "AXPopUpButton", "AXMenuButton", "AXTextField", "AXTextArea",
        "AXComboBox", "AXLink", "AXMenuItem", "AXSlider", "AXDisclosureTriangle", "AXCell", "AXSearchField",
        "AXIncrementor", "AXSecureTextField",
    ]
    static let textRoles: Set<String> = ["AXStaticText", "AXHeading", "AXTextField", "AXTextArea", "AXCell"]

    struct Limits {
        var elements = 3000
        var characters = 10000
        var seconds = 1.5
        var depth = 60
    }

    /// Visits the window's elements breadth first until `visit` returns false or a limit is hit.
    static func walk(_ root: AXUIElement, limits: Limits = Limits(), visit: (AXUIElement, Int) -> Bool) {
        let deadline = Date().addingTimeInterval(limits.seconds)
        var queue: [(AXUIElement, Int)] = [(root, 0)]
        var seen = 0
        while !queue.isEmpty, seen < limits.elements, Date() < deadline {
            let (element, depth) = queue.removeFirst()
            seen += 1
            guard visit(element, depth) else { return }
            if depth < limits.depth { queue += children(element).map { ($0, depth + 1) } }
        }
    }

    /// The visible text of a window as lines, capped. Secure fields are skipped.
    static func text(of window: AXUIElement, limit: Int = 8000) -> String {
        var lines: [String] = []
        var total = 0
        walk(window) { element, _ in
            let role = role(element)
            guard !isSecure(element) else { return true }
            var line: String?
            if textRoles.contains(role) {
                line = string(element, kAXValueAttribute) ?? string(element, kAXTitleAttribute)
            } else if actionable.contains(role) {
                line = string(element, kAXTitleAttribute) ?? string(element, kAXDescriptionAttribute)
            }
            if let line, line != lines.last {
                lines.append(clip(line, 600))
                total += line.count + 1
            }
            return total < limit
        }
        return lines.joined(separator: "\n")
    }

    static func clip(_ text: String, _ n: Int) -> String {
        let flat = text.split(whereSeparator: \.isNewline).joined(separator: " ")
        return flat.count <= n ? flat : String(flat.prefix(n - 1)) + "…"
    }
}
