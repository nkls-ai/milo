import AppKit

/// The milo-mac actions, run with Milo's own Accessibility and Screen Recording permissions.
///
/// The brain has already checked and, if needed, asked about each action. This only does it, on a serial
/// queue so a slow app never blocks the main thread. Every event it posts carries
/// PasteboardInserter.eventMarker, so the key monitor and takeover detection know it was Milo.
public final class MacHands: HandsExecutor {
    private let shots: ScreenShots
    private let apps: FrontApps
    private let queue = DispatchQueue(label: "milo.hands")
    /// ax_tree element ids, valid until the next ax_tree.
    private var elements: [String: AXUIElement] = [:]
    /// The last screenshot, so click and scroll can turn its pixels into screen points.
    private var lastShot: ScreenShots.Shot?
    /// The app that had the keyboard focus when type or key was checked; the action refuses if it moved.
    private var checkedFocus: pid_t?
    private var script: Process?
    private let lock = NSLock()

    public convenience init(screensFolder: URL) {
        self.init(shots: ScreenShots(folder: screensFolder), apps: FrontApps())
    }

    init(shots: ScreenShots, apps: FrontApps) {
        self.shots = shots
        self.apps = apps
    }

    public func perform(_ tool: String, args: [String: JSONValue],
                        completion: @escaping (Result<[String: JSONValue], HandsFailure>) -> Void) {
        let front = apps.front()
        queue.async { [self] in
            let finish = { (result: Result<[String: JSONValue], HandsFailure>) in
                DispatchQueue.main.async { completion(result) }
            }
            if tool == "screenshot" {
                return screenshot(front: front, finish: finish)
            }
            do {
                finish(.success(try run(tool, args, front: front)))
            } catch let failure as HandsFailure {
                finish(.failure(failure))
            } catch {
                finish(.failure(HandsFailure(error.localizedDescription)))
            }
        }
    }

    public func cancel() {
        lock.lock()
        let running = script
        lock.unlock()
        if let running, running.isRunning { running.terminate() }
    }

    // MARK: Actions

    private func run(_ tool: String, _ args: [String: JSONValue], front: NSRunningApplication?) throws -> [String: JSONValue] {
        if tool != "list_apps" && tool != "open_app" && tool != "run_applescript" && !AXIsProcessTrusted() {
            throw HandsFailure(AX.notTrusted)
        }
        switch tool {
        case "describe": return describe(args, front: front)
        case "list_apps": return ["text": .string(listApps())]
        case "open_app": return try openApp(try text(args, "name"))
        case "window_text":
            let (app, window) = try window(args, front: front)
            return ["text": .string(AX.text(of: window, limit: 16000)), "summary": .string(summary(app, window))]
        case "ax_tree":
            let (app, window) = try window(args, front: front)
            return ["text": .string(tree(window)),
                    "summary": .string(summary(app, window) + ". Element ids are valid until the next ax_tree.")]
        case "ax_press": return try press(try element(args))
        case "ax_set_value": return try setValue(try element(args), try text(args, "text"))
        case "run_applescript": return try appleScript(try text(args, "script"))
        case "click": return try click(args)
        case "type": return try type(try text(args, "text"))
        case "key": return try key(try text(args, "combo"))
        case "scroll": return try scroll(args)
        default: throw HandsFailure("Milo has no action called \(tool).")
        }
    }

    /// What an action would touch, for the brain's safety check and for Milo to fly to.
    private func describe(_ args: [String: JSONValue], front: NSRunningApplication?) -> [String: JSONValue] {
        var element: AXUIElement?
        var point: CGPoint?
        switch args["tool"]?.string {
        case "click", "scroll":
            if let x = args["x"]?.number, let y = args["y"]?.number, let shot = lastShot {
                point = shot.point(x: x, y: y)
            } else if args["tool"]?.string == "scroll" {
                point = Self.pointerLocation()
            }
            element = point.flatMap(AX.element)
            if element == nil, let point, args["tool"]?.string == "click" {
                // The brain still checks the app: a secret one among them is never clicked.
                let owners = AX.owners(at: point)
                let owner = owners.first(where: AX.isSecret) ?? owners.last ?? front
                return ["unresolved": true, "app": .string(owner?.localizedName ?? ""),
                        "bundle": .string(owner?.bundleIdentifier ?? ""),
                        "point": .object(["x": .number(point.x), "y": .number(point.y)])]
            }
        case "ax_press", "ax_set_value":
            element = args["element"]?.string.flatMap { elements[$0] }
            point = element.flatMap(AX.frame).map { CGPoint(x: $0.midX, y: $0.midY) }
        case "type", "key":
            element = AX.focused()
            checkedFocus = element.map(AX.pid)
            point = element.flatMap(AX.frame).map { CGPoint(x: $0.midX, y: $0.midY) }
        case "open_app":
            let name = args["name"]?.string ?? ""
            let running = Self.running(name)
            return ["app": .string(name), "bundle": .string(running?.bundleIdentifier ?? "")]
        default:
            break
        }
        var info: [String: JSONValue] = [:]
        if let element {
            let owner = NSRunningApplication(processIdentifier: AX.pid(element))
            info["app"] = .string(owner?.localizedName ?? "")
            info["bundle"] = .string(owner?.bundleIdentifier ?? "")
            info["title"] = .string(AX.label(element))
            info["role"] = .string(AX.roleName(element))
            info["secure"] = .bool(AX.isSecure(element))
        } else {
            info["app"] = .string(front?.localizedName ?? "")
            info["bundle"] = .string(front?.bundleIdentifier ?? "")
        }
        if let point { info["point"] = .object(["x": .number(point.x), "y": .number(point.y)]) }
        return info
    }

    private func listApps() -> String {
        let front = NSWorkspace.shared.frontmostApplication
        return NSWorkspace.shared.runningApplications
            .filter { $0.activationPolicy == .regular && $0.processIdentifier != getpid() }
            .map { app in
                var line = app.localizedName ?? app.bundleIdentifier ?? "?"
                if app == front { line += " (in front)" } else if app.isHidden { line += " (hidden)" }
                return line
            }
            .joined(separator: "\n")
    }

    private func openApp(_ name: String) throws -> [String: JSONValue] {
        if let app = Self.running(name) {
            app.unhide()
            app.activate()
            return ["text": .string("Brought \(app.localizedName ?? name) to the front.")]
        }
        let open = Process()
        open.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        open.arguments = ["-a", name]
        open.standardOutput = FileHandle.nullDevice
        open.standardError = FileHandle.nullDevice
        try open.run()
        open.waitUntilExit()
        guard open.terminationStatus == 0 else { throw HandsFailure("There is no app called \(name).") }
        Thread.sleep(forTimeInterval: 1)  // give it a moment to put up a window
        return ["text": .string("Opened \(name).")]
    }

    private func window(_ args: [String: JSONValue], front: NSRunningApplication?) throws -> (NSRunningApplication, AXUIElement) {
        let app = try args["app"]?.string.map { name in
            guard let app = Self.running(name) else { throw HandsFailure("\(name) isn't open. Use open_app first.") }
            return app
        } ?? front
        guard let app else { throw HandsFailure("No app is in front.") }
        guard !AX.isSecret(app) else { throw HandsFailure(AX.secretRefused) }
        guard let window = AX.window(of: AX.application(app.processIdentifier)) else {
            throw HandsFailure("\(app.localizedName ?? "That app") has no window open.")
        }
        return (app, window)
    }

    private func summary(_ app: NSRunningApplication, _ window: AXUIElement) -> String {
        [app.localizedName, AX.string(window, kAXTitleAttribute)].compactMap { $0 }.joined(separator: ", ")
    }

    /// One line per control or text: `e12 button “Save”`, `e13 text field “Name” = Bob`.
    private func tree(_ window: AXUIElement) -> String {
        var lines: [String] = []
        var found: [String: AXUIElement] = [:]
        var chars = 0
        AX.walk(window) { element, depth in
            let role = AX.role(element)
            let interesting = AX.actionable.contains(role) || AX.textRoles.contains(role)
            guard interesting else { return true }
            let label = AX.label(element)
            if !AX.actionable.contains(role) && label.isEmpty { return true }
            let id = "e\(found.count + 1)"
            found[id] = element
            var line = String(repeating: " ", count: min(depth, 12)) + "\(id) \(SystemScreenReader.describe(element))"
            if AX.isSecure(element) { line += " (never read)" }
            if (AX.attribute(element, kAXEnabledAttribute) as Bool?) == false { line += " (disabled)" }
            lines.append(line)
            chars += line.count + 1
            return found.count < 400 && chars < 14000
        }
        elements = found
        return lines.isEmpty ? "This window shows no controls Milo can read." : lines.joined(separator: "\n")
    }

    private func element(_ args: [String: JSONValue]) throws -> AXUIElement {
        let id = try text(args, "element")
        guard let element = elements[id] else { throw HandsFailure("There is no element \(id). Call ax_tree again.") }
        return element
    }

    private func press(_ element: AXUIElement) throws -> [String: JSONValue] {
        for action in [kAXPressAction, kAXPickAction, kAXConfirmAction, kAXShowMenuAction] {
            if AXUIElementPerformAction(element, action as CFString) == .success {
                return ["text": .string("Pressed “\(AX.label(element))”.")]
            }
        }
        throw HandsFailure("That element can't be pressed. Try click with a screenshot.")
    }

    private func setValue(_ element: AXUIElement, _ value: String) throws -> [String: JSONValue] {
        guard !AX.isSecure(element) else { throw HandsFailure("Milo never fills in password fields.") }
        AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
        guard AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, value as CFString) == .success else {
            throw HandsFailure("That field can't be set directly. Click into it and use type.")
        }
        return ["text": .string("Filled in “\(AX.label(element))”.")]
    }

    private func appleScript(_ source: String) throws -> [String: JSONValue] {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-"]
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors
        try process.run()
        lock.lock()
        script = process
        lock.unlock()
        defer {
            lock.lock()
            script = nil
            lock.unlock()
        }
        input.fileHandleForWriting.write(Data(source.utf8))
        try? input.fileHandleForWriting.close()
        let deadline = DispatchTime.now() + 30
        DispatchQueue.global().asyncAfter(deadline: deadline) { if process.isRunning { process.terminate() } }
        let out = output.fileHandleForReading.readDataToEndOfFile()
        let err = errors.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let text = String(decoding: out, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        guard process.terminationStatus == 0 else {
            if process.terminationReason == .uncaughtSignal { throw HandsFailure("The script was stopped.") }
            let why = String(decoding: err, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            throw HandsFailure("The script failed: \(why.isEmpty ? "exit \(process.terminationStatus)" : why)")
        }
        return ["text": .string(String(text.prefix(16000)))]
    }

    private func screenshot(front: NSRunningApplication?, finish: @escaping (Result<[String: JSONValue], HandsFailure>) -> Void) {
        if AX.isSecret(front) { return finish(.failure(HandsFailure(AX.secretRefused))) }
        var center: CGPoint?
        if AXIsProcessTrusted(), let front, let window = AX.window(of: AX.application(front.processIdentifier)),
           let frame = AX.frame(window) {
            center = CGPoint(x: frame.midX, y: frame.midY)
        }
        Task { [shots] in
            do {
                let shot = try await shots.display(containing: center)
                queue.async { self.lastShot = shot }
                finish(.success(["image": .string(shot.url.path), "width": .number(Double(shot.width)),
                                 "height": .number(Double(shot.height))]))
            } catch let failure as ScreenShots.Failure {
                finish(.failure(HandsFailure(failure.message)))
            } catch {
                finish(.failure(HandsFailure(error.localizedDescription)))
            }
        }
    }

    private func click(_ args: [String: JSONValue]) throws -> [String: JSONValue] {
        let point = try screenPoint(args)
        if AX.owners(at: point).contains(where: AX.isSecret) { throw HandsFailure(AX.secretRefused) }
        let right = args["button"]?.string == "right"
        let clicks = args["double"]?.bool == true ? 2 : 1
        let (down, up): (CGEventType, CGEventType) = right ? (.rightMouseDown, .rightMouseUp) : (.leftMouseDown, .leftMouseUp)
        post(CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left))
        for n in 1...clicks {
            for type in [down, up] {
                let event = CGEvent(mouseEventSource: nil, mouseType: type, mouseCursorPosition: point,
                                    mouseButton: right ? .right : .left)
                event?.setIntegerValueField(.mouseEventClickState, value: Int64(n))
                post(event)
            }
        }
        return ["text": .string(clicks == 2 ? "Double-clicked." : "Clicked.")]
    }

    /// The keyboard goes where it was checked to go, and never into a password field or a password app.
    private func checkFocus(allowSecure: Bool = false) throws {
        let focused = AX.focused()
        if let checked = checkedFocus, focused.map(AX.pid) != checked {
            throw HandsFailure("The keyboard focus moved to another app since I checked. Look again first.")
        }
        if let focused, AX.isSecret(NSRunningApplication(processIdentifier: AX.pid(focused))) {
            throw HandsFailure(AX.secretRefused)
        }
        if !allowSecure, let focused, AX.isSecure(focused) {
            throw HandsFailure("Milo never types into password fields.")
        }
    }

    private func type(_ text: String) throws -> [String: JSONValue] {
        try checkFocus()
        let units = Array(text.utf16)
        for start in stride(from: 0, to: units.count, by: 16) {
            let chunk = Array(units[start..<min(start + 16, units.count)])
            for down in [true, false] {
                let event = CGEvent(keyboardEventSource: nil, virtualKey: 0, keyDown: down)
                event?.keyboardSetUnicodeString(stringLength: chunk.count, unicodeString: chunk)
                post(event)
            }
            usleep(8000)
        }
        return ["text": "Typed."]
    }

    private func key(_ combo: String) throws -> [String: JSONValue] {
        guard let parsed = KeyCombo(combo) else {
            throw HandsFailure("I don't know the key \(combo). Use names like return, tab, escape, cmd+s.")
        }
        // In a password field only moving on is allowed: tab, shift+tab, escape.
        let movesOn = [48, 53].contains(parsed.keyCode) && parsed.modifiers.subtracting(.shift).isEmpty
        try checkFocus(allowSecure: movesOn)
        var flags: CGEventFlags = []
        if parsed.modifiers.contains(.command) { flags.insert(.maskCommand) }
        if parsed.modifiers.contains(.shift) { flags.insert(.maskShift) }
        if parsed.modifiers.contains(.option) { flags.insert(.maskAlternate) }
        if parsed.modifiers.contains(.control) { flags.insert(.maskControl) }
        for down in [true, false] {
            let event = CGEvent(keyboardEventSource: nil, virtualKey: parsed.keyCode, keyDown: down)
            event?.flags = flags
            post(event)
        }
        return ["text": .string("Pressed \(parsed.displayName).")]
    }

    private func scroll(_ args: [String: JSONValue]) throws -> [String: JSONValue] {
        if args["x"] != nil || args["y"] != nil {
            post(CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: try screenPoint(args),
                         mouseButton: .left))
        }
        let dy = Int32(-(args["dy"]?.number ?? 0)), dx = Int32(-(args["dx"]?.number ?? 0))
        post(CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 2, wheel1: dy, wheel2: dx, wheel3: 0))
        return ["text": "Scrolled."]
    }

    // MARK: Helpers

    private func screenPoint(_ args: [String: JSONValue]) throws -> CGPoint {
        guard let shot = lastShot else { throw HandsFailure("Take a screenshot first: x and y are its pixels.") }
        guard let x = args["x"]?.number, let y = args["y"]?.number,
              x >= 0, y >= 0, x <= Double(shot.width), y <= Double(shot.height) else {
            throw HandsFailure("x and y must lie inside the last screenshot (\(shot.width)x\(shot.height)).")
        }
        return shot.point(x: x, y: y)
    }

    private func post(_ event: CGEvent?) {
        event?.setIntegerValueField(.eventSourceUserData, value: PasteboardInserter.eventMarker)
        event?.post(tap: .cghidEventTap)
    }

    private func text(_ args: [String: JSONValue], _ name: String) throws -> String {
        guard let value = args[name]?.string else { throw HandsFailure("\(name) is missing.") }
        return value
    }

    static func running(_ name: String) -> NSRunningApplication? {
        let wanted = name.lowercased().replacingOccurrences(of: ".app", with: "")
        return NSWorkspace.shared.runningApplications.first {
            $0.localizedName?.lowercased() == wanted || $0.bundleIdentifier?.lowercased() == wanted
        }
    }

    /// The pointer in global points, origin top-left.
    static func pointerLocation() -> CGPoint {
        CGEvent(source: nil)?.location ?? .zero
    }
}
