import AppKit
import UniformTypeIdentifiers

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
    /// The exact element that had focus when type or key was checked; typing refuses if focus moved off it.
    private var checkedElement: AXUIElement?
    private var script: Process?
    private let lock = NSLock()
    private var lent: Set<String> = []
    /// Where a sandboxed app may save without macOS asking (AccessSource.places), for the script guard.
    private let places: (AccessApp) -> [String]?

    /// The devices the user lent ("mouse", "keyboard"); set on the main queue, read on the hands queue. An
    /// action falls back to the real pointer or keyboard only for a device that was actually lent, so a yes to
    /// borrowing the mouse never quietly lets Milo type with the real keyboard.
    public var borrowed: Set<String> {
        get { lock.lock(); defer { lock.unlock() }; return lent }
        set { lock.lock(); lent = newValue; lock.unlock() }
    }

    private func lent(_ need: Delivery.Need) -> Bool { borrowed.contains(need.rawValue) }

    /// `places`: where an app can save without macOS stopping it to ask for file access; nil for anywhere.
    public convenience init(screensFolder: URL, places: @escaping (AccessApp) -> [String]? = { _ in nil }) {
        self.init(shots: ScreenShots(folder: screensFolder), apps: FrontApps(), places: places)
    }

    init(shots: ScreenShots, apps: FrontApps, places: @escaping (AccessApp) -> [String]? = { _ in nil }) {
        self.shots = shots
        self.apps = apps
        self.places = places
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
        if Self.needsAccessibility(tool, args) && !AXIsProcessTrusted() {
            throw HandsFailure(AX.notTrusted)
        }
        switch tool {
        case "describe": return describe(args, front: front)
        case "list_apps": return ["text": .string(listApps())]
        case "open_app": return try openApp(try text(args, "name"))
        case "open_url": return try openURL(try text(args, "url"), app: args["app"]?.string)
        case "open_file": return try openFile(try text(args, "path"))
        case "focus_app": return try focusApp(try text(args, "app"))
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

    /// Whether an action reads or works another app's window. Scripts, opening apps and describing those don't, so
    /// they work without Accessibility.
    static func needsAccessibility(_ tool: String, _ args: [String: JSONValue]) -> Bool {
        let free: Set<String> = ["list_apps", "open_app", "open_url", "open_file", "focus_app", "run_applescript"]
        return !free.contains(tool == "describe" ? args["tool"]?.string ?? "" : tool)
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
            checkedElement = element
            point = element.flatMap(Self.caret) ?? element.flatMap(AX.frame).map { CGPoint(x: $0.midX, y: $0.midY) }
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
            // Milo's own window (his bubble, his conversation): the brain refuses to act there.
            if AX.pid(element) == getpid() { info["milo"] = true }
            // The window it sits in, for the outline and for Pip to perch on.
            if let window = Self.window(of: element), let frame = AX.frame(window) {
                info["window"] = HandsTarget.json(frame)
                info["pid"] = .number(Double(AX.pid(element)))
            }
        } else {
            info["app"] = .string(front?.localizedName ?? "")
            info["bundle"] = .string(front?.bundleIdentifier ?? "")
            if front?.processIdentifier == getpid() { info["milo"] = true }
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

    /// How long opening waits for the app to be in front with a window before it answers anyway.
    static let frontWait: TimeInterval = 2

    /// Opens the app, or brings it forward if it runs: `open -a` goes through Launch Services, which activates it
    /// even while Milo isn't the active app, and asks a running app without windows for a new one (as a click on
    /// its Dock icon does). Then waits until it is in front with a window.
    private func openApp(_ name: String) throws -> [String: JSONValue] {
        guard try launchServices(["-a", name]) else { throw HandsFailure("There is no app called \(name).") }
        return arrived(name: name, bundle: nil, done: "Opened \(name)")
    }

    /// Opens a web page, in `app` if named (e.g. "Google Chrome"), else in the default browser, and waits until
    /// that browser is in front with a window.
    private func openURL(_ text: String, app: String?) throws -> [String: JSONValue] {
        if let refused = OpenGuard.refuses(url: text) { throw HandsFailure(refused) }
        guard let url = URL(string: text) else { throw HandsFailure("That isn't a web address.") }
        let site = url.host ?? text
        if let app, !app.isEmpty {
            // Only an app that opens web pages: handing an address to some other app (a terminal) could run it.
            let browsers = NSWorkspace.shared.urlsForApplications(toOpen: url)
            guard let browser = browsers.first(where: { Self.names($0, app) }) else {
                throw HandsFailure("\(app) doesn't open web pages, or isn't installed.")
            }
            guard try launchServices(["-a", browser.path, text]) else { throw HandsFailure("Couldn't open \(site).") }
            return arrived(name: app, bundle: Bundle(url: browser)?.bundleIdentifier, done: "Opened \(site) in \(app)")
        }
        let browser = NSWorkspace.shared.urlForApplication(toOpen: url).flatMap { Bundle(url: $0)?.bundleIdentifier }
        guard try launchServices([text]) else { throw HandsFailure("Couldn't open \(site).") }
        return arrived(name: nil, bundle: browser, done: "Opened \(site)")
    }

    /// Opens a document or folder in the app the system opens it with, never a named one (a terminal would run a
    /// text file), and never a file that would run code itself (OpenGuard.refuses).
    private func openFile(_ path: String) throws -> [String: JSONValue] {
        // What is opened is what the link or alias points to, so that is what gets checked.
        var url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath).resolvingSymlinksInPath()
        if (try? url.resourceValues(forKeys: [.isAliasFileKey]))?.isAliasFile == true {
            guard let target = try? URL(resolvingAliasFileAt: url, options: [.withoutUI, .withoutMounting]) else {
                throw HandsFailure("\(url.lastPathComponent) is an alias Milo can't follow.")
            }
            url = target.resolvingSymlinksInPath()
        }
        let full = url.path
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: full, isDirectory: &isDirectory) else {
            throw HandsFailure("There is no file or folder at \(path).")
        }
        let type = (try? url.resourceValues(forKeys: [.contentTypeKey]))?.contentType
        let types = type.map { [$0.identifier] + $0.supertypes.map(\.identifier) } ?? []
        if let refused = OpenGuard.refuses(path: full, isDirectory: isDirectory.boolValue, types: types,
                                         executable: FileManager.default.isExecutableFile(atPath: full)
                                             && !isDirectory.boolValue) {
            throw HandsFailure(refused)
        }
        let opener = NSWorkspace.shared.urlForApplication(toOpen: url).flatMap { Bundle(url: $0)?.bundleIdentifier }
        guard try launchServices([full]) else { throw HandsFailure("Couldn't open \(url.lastPathComponent).") }
        return arrived(name: nil, bundle: opener, done: "Opened \(url.lastPathComponent)")
    }

    /// Brings a running app to the front before a key, typing or a click goes to it, and says whether it got there.
    /// Never Milo himself.
    private func focusApp(_ name: String) throws -> [String: JSONValue] {
        guard let app = Self.running(name) else { throw HandsFailure("\(name) isn't open. Use open_app first.") }
        if app.processIdentifier == getpid() { throw HandsFailure("Milo never acts in his own window.") }
        let pid = app.processIdentifier
        let isFront = { NSWorkspace.shared.frontmostApplication?.processIdentifier == pid }
        if !isFront() {
            app.unhide()
            app.activate()
            // macOS may ignore activate() from an app that isn't active itself; Launch Services is listened to.
            if !OpenGuard.wait(timeout: 0.4, isFront), let bundle = app.bundleURL {
                _ = try? launchServices(["-a", bundle.path])
            }
        }
        let front = OpenGuard.wait(timeout: Self.frontWait, isFront)
        return ["app": .string(app.localizedName ?? name), "bundle": .string(app.bundleIdentifier ?? ""),
                "front": .bool(front)]
    }

    /// Runs `open` with these arguments. False when it says it couldn't (no such app, nothing to open with).
    private func launchServices(_ arguments: [String]) throws -> Bool {
        let open = Process()
        open.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        open.arguments = arguments
        open.standardOutput = FileHandle.nullDevice
        open.standardError = FileHandle.nullDevice
        try open.run()
        open.waitUntilExit()
        return open.terminationStatus == 0
    }

    /// Waits (at most `frontWait`) until the app with this bundle id or name is in front with a window on screen,
    /// and says what happened. `front` false means it opened but isn't in front yet.
    private func arrived(name: String?, bundle: String?, done: String) -> [String: JSONValue] {
        let wanted = name.map { $0.lowercased().replacingOccurrences(of: ".app", with: "") }
        let matches = { (app: NSRunningApplication) -> Bool in
            if let bundle, app.bundleIdentifier == bundle { return true }
            guard let wanted else { return false }
            return app.localizedName?.lowercased() == wanted || app.bundleIdentifier?.lowercased() == wanted
        }
        var found: NSRunningApplication?
        let front = OpenGuard.wait(timeout: Self.frontWait) {
            guard let app = NSWorkspace.shared.frontmostApplication, matches(app) else { return false }
            found = app
            return Self.hasWindow(app.processIdentifier)
        }
        let app = found ?? NSWorkspace.shared.runningApplications.first(where: matches)
        let label = app?.localizedName ?? name ?? ""
        return ["text": .string(front ? "\(done)." : "\(done), but it isn't in front yet."),
                "app": .string(label), "bundle": .string(app?.bundleIdentifier ?? bundle ?? ""), "front": .bool(front)]
    }

    /// Milo never presses, fills in or types into his own windows (his Yes and Allow buttons among them), whoever
    /// asks: the brain refuses first, and this is the second lock.
    static func notMilo(_ element: AXUIElement) throws {
        if AX.pid(element) == getpid() { throw HandsFailure("Milo never acts in his own window.") }
    }

    /// Whether the app at `url` is the one called `name` (its file name or its bundle id), any case.
    static func names(_ url: URL, _ name: String) -> Bool {
        let wanted = name.lowercased().replacingOccurrences(of: ".app", with: "")
        let file = url.deletingPathExtension().lastPathComponent.lowercased()
        return file == wanted || Bundle(url: url)?.bundleIdentifier?.lowercased() == wanted
    }

    /// Whether the process has a normal window on screen. The window list says that without Screen Recording.
    static func hasWindow(_ pid: pid_t) -> Bool {
        guard let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
                as? [[String: Any]] else { return false }
        return list.contains { $0[kCGWindowOwnerPID as String] as? pid_t == pid && $0[kCGWindowLayer as String] as? Int == 0 }
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
        try Self.notMilo(element)
        for action in [kAXPressAction, kAXPickAction, kAXConfirmAction, kAXShowMenuAction] {
            if AXUIElementPerformAction(element, action as CFString) == .success {
                return ["text": .string("Pressed “\(AX.label(element))”.")]
            }
        }
        throw HandsFailure("That element can't be pressed. Try click with a screenshot.")
    }

    private func setValue(_ element: AXUIElement, _ value: String) throws -> [String: JSONValue] {
        try Self.notMilo(element)
        guard !AX.isSecure(element) else { throw HandsFailure("Milo never fills in password fields.") }
        AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue)
        guard AXUIElementSetAttributeValue(element, kAXValueAttribute as CFString, value as CFString) == .success else {
            throw HandsFailure("That field can't be set directly. Click into it and use type.")
        }
        return ["text": .string("Filled in “\(AX.label(element))”.")]
    }

    private func appleScript(_ source: String) throws -> [String: JSONValue] {
        // A sandboxed app saving outside its folders would stop at macOS's file access question (ADR 25).
        if let refusal = SandboxGuard.refusal(script: source, places: places) { throw HandsFailure(refusal) }
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
        let deadline = DispatchTime.now() + 30
        DispatchQueue.global().asyncAfter(deadline: deadline) { if process.isRunning { process.terminate() } }
        let (out, err) = Self.collect(process, input: Data(source.utf8), output: output, errors: errors)
        let text = String(decoding: out, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        guard process.terminationStatus == 0 else {
            if process.terminationReason == .uncaughtSignal { throw HandsFailure("The script was stopped.") }
            let why = String(decoding: err, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            throw HandsFailure("The script failed: \(why.isEmpty ? "exit \(process.terminationStatus)" : why)")
        }
        return ["text": .string(String(text.prefix(16000)))]
    }

    /// Writes `input`, then reads stdout and stderr to the end at the same time and waits for the exit. Read
    /// one after the other, a child that fills the other pipe (64 KB of `log` output) blocks forever.
    static func collect(_ process: Process, input: Data, output: Pipe, errors: Pipe) -> (Data, Data) {
        let group = DispatchGroup()
        var err = Data()
        group.enter()
        DispatchQueue.global().async {
            err = errors.fileHandleForReading.readDataToEndOfFile()
            group.leave()
        }
        if let stdin = process.standardInput as? Pipe {
            stdin.fileHandleForWriting.write(input)
            try? stdin.fileHandleForWriting.close()
        }
        let out = output.fileHandleForReading.readDataToEndOfFile()
        group.wait()
        process.waitUntilExit()
        return (out, err)
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
        let element = AX.element(at: point)
        let pressable = element.flatMap(Self.pressable)
        var traits = Delivery.Traits()
        traits.pressable = pressable != nil
        traits.textual = element.map { AX.textRoles.contains(AX.role($0)) && AX.role($0) != "AXStaticText" } ?? false
        traits.menu = element.map { Self.actions($0).contains(kAXShowMenuAction) } ?? false
        let steps = Delivery.plan(.click(right: right, count: clicks), traits: traits, family: family(of: element),
                                  borrowed: lent(.mouse))
        for step in steps {
            switch step {
            case .axPress:
                if let pressable, AXUIElementPerformAction(pressable, kAXPressAction as CFString) == .success {
                    return Self.done("Clicked “\(AX.label(pressable))” in the background.", route: "ax")
                }
            case .axFocus:
                if let element, Self.focus(element, at: point) {
                    return Self.done("Clicked into the field in the background.", route: "ax")
                }
            case .axShowMenu:
                if let element, AXUIElementPerformAction(element, kAXShowMenuAction as CFString) == .success {
                    return Self.done("Opened the menu in the background.", route: "ax")
                }
            case .real:
                realClick(at: point, right: right, clicks: clicks)
                return Self.done(clicks == 2 ? "Double-clicked." : "Clicked.", route: "real")
            case .axInsert, .axScrollBar:
                break
            }
        }
        throw HandsFailure("This click needs the real mouse.", borrow: Delivery.need(for: .click(right: right, count: clicks)).rawValue)
    }

    /// The user's pointer, lent: it clicks and then goes back to where the user left it.
    private func realClick(at point: CGPoint, right: Bool, clicks: Int) {
        let rest = Self.pointerLocation()
        defer { CGWarpMouseCursorPosition(rest) }
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
    }

    /// The keyboard goes to the exact element that had focus when the action was checked (`describe`), never a
    /// different one that stole focus since, and never a password field or a password app. Returns that element.
    @discardableResult
    private func checkFocus(allowSecure: Bool = false) throws -> AXUIElement? {
        let focused = AX.focused()
        if let focused { try Self.notMilo(focused) }
        if let checked = checkedFocus, focused.map(AX.pid) != checked {
            throw HandsFailure("The keyboard focus moved to another app since I checked. Look again first.")
        }
        if let checked = checkedElement, let focused, !CFEqual(checked, focused) {
            throw HandsFailure("The keyboard focus moved to another field since I checked. Look again first.")
        }
        if let focused, AX.isSecret(NSRunningApplication(processIdentifier: AX.pid(focused))) {
            throw HandsFailure(AX.secretRefused)
        }
        if !allowSecure, let focused, AX.isSecure(focused) {
            throw HandsFailure("Milo never types into password fields.")
        }
        return focused
    }

    private func type(_ text: String) throws -> [String: JSONValue] {
        // The same element throughout: checked for focus and secrecy, then written to.
        let focused = try checkFocus()
        var traits = Delivery.Traits()
        traits.insertable = focused.map { Self.settable($0, kAXSelectedTextAttribute) } ?? false
        for step in Delivery.plan(.type, traits: traits, family: family(of: focused), borrowed: lent(.keyboard)) {
            switch step {
            case .axInsert:
                if let focused, Self.insert(text, into: focused) { return Self.done("Typed in the background.", route: "ax") }
            case .real:
                realType(text)
                return Self.done("Typed.", route: "real")
            default:
                break
            }
        }
        throw HandsFailure("Typing here needs the real keyboard.", borrow: Delivery.need(for: .type).rawValue)
    }

    private func realType(_ text: String) {
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
    }

    private func key(_ combo: String) throws -> [String: JSONValue] {
        guard let parsed = KeyCombo(combo) else {
            throw HandsFailure("I don't know the key \(combo). Use names like return, tab, escape, cmd+s.")
        }
        // In a password field only moving on is allowed: tab, shift+tab, escape.
        let movesOn = [48, 53].contains(parsed.keyCode) && parsed.modifiers.subtracting(.shift).isEmpty
        try checkFocus(allowSecure: movesOn)
        guard lent(.keyboard) else {
            throw HandsFailure("Pressing keys needs the real keyboard.", borrow: Delivery.need(for: .key).rawValue)
        }
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
        return Self.done("Pressed \(parsed.displayName).", route: "real")
    }

    private func scroll(_ args: [String: JSONValue]) throws -> [String: JSONValue] {
        let point = args["x"] != nil || args["y"] != nil ? try screenPoint(args) : nil
        let lines = (dx: args["dx"]?.number ?? 0, dy: args["dy"]?.number ?? 0)
        let area = AX.element(at: point ?? Self.pointerLocation()).flatMap(Self.scrollArea)
        var traits = Delivery.Traits()
        traits.scrollBar = area != nil
        for step in Delivery.plan(.scroll, traits: traits, family: .cocoa, borrowed: lent(.mouse)) {
            switch step {
            case .axScrollBar:
                if let area, Self.scroll(area, lines: lines) { return Self.done("Scrolled in the background.", route: "ax") }
            case .real:
                let rest = Self.pointerLocation()
                defer { CGWarpMouseCursorPosition(rest) }
                if let point {
                    post(CGEvent(mouseEventSource: nil, mouseType: .mouseMoved, mouseCursorPosition: point, mouseButton: .left))
                }
                let dy = Int32(-lines.dy), dx = Int32(-lines.dx)
                post(CGEvent(scrollWheelEvent2Source: nil, units: .line, wheelCount: 2, wheel1: dy, wheel2: dx, wheel3: 0))
                return Self.done("Scrolled.", route: "real")
            default:
                break
            }
        }
        throw HandsFailure("Scrolling here needs the real mouse.", borrow: Delivery.need(for: .scroll).rawValue)
    }

    // MARK: Background, through Accessibility

    private static func done(_ text: String, route: String) -> [String: JSONValue] {
        ["text": .string(text), "route": .string(route)]
    }

    private func family(of element: AXUIElement?) -> Delivery.Family {
        let app = element.map { NSRunningApplication(processIdentifier: AX.pid($0)) } ?? nil
        let frameworks = app?.bundleURL?.appendingPathComponent("Contents/Frameworks")
        let embeds = ["Electron Framework.framework", "Chromium Embedded Framework.framework"].contains { name in
            frameworks.map { FileManager.default.fileExists(atPath: $0.appendingPathComponent(name).path) } ?? false
        }
        return Delivery.family(bundleID: app?.bundleIdentifier, embedsChromium: embeds)
    }

    private static func actions(_ element: AXUIElement) -> [String] {
        var names: CFArray?
        AXUIElementCopyActionNames(element, &names)
        return names as? [String] ?? []
    }

    private static func settable(_ element: AXUIElement, _ attribute: String) -> Bool {
        var yes: DarwinBoolean = false
        return AXUIElementIsAttributeSettable(element, attribute as CFString, &yes) == .success && yes.boolValue
    }

    /// The element or one of its two nearest ancestors that presses: a click on a button's label presses it.
    private static func pressable(_ element: AXUIElement) -> AXUIElement? {
        var node: AXUIElement? = element
        for _ in 0..<3 {
            guard let current = node else { return nil }
            if AX.actionable.contains(AX.role(current)) && actions(current).contains(kAXPressAction) { return current }
            node = AX.attribute(current, kAXParentAttribute)
        }
        return nil
    }

    /// Focuses a text element and puts the caret under `point`, read back to check.
    private static func focus(_ element: AXUIElement, at point: CGPoint) -> Bool {
        guard !AX.isSecure(element),
              AXUIElementSetAttributeValue(element, kAXFocusedAttribute as CFString, kCFBooleanTrue) == .success
        else { return false }
        var spot = point
        var value: CFTypeRef?
        if let position = AXValueCreate(.cgPoint, &spot),
           AXUIElementCopyParameterizedAttributeValue(element, kAXRangeForPositionParameterizedAttribute as CFString,
                                                      position, &value) == .success,
           let value, CFGetTypeID(value) == AXValueGetTypeID() {
            var range = CFRange()
            AXValueGetValue(value as! AXValue, .cfRange, &range)
            var caret = CFRange(location: range.location, length: 0)
            if let caretValue = AXValueCreate(.cfRange, &caret) {
                AXUIElementSetAttributeValue(element, kAXSelectedTextRangeAttribute as CFString, caretValue)
            }
        }
        return (AX.attribute(element, kAXFocusedAttribute) as Bool?) ?? true
    }

    /// Inserts text at the caret and waits briefly to read it back: some apps say yes and do nothing.
    private static func insert(_ text: String, into element: AXUIElement) -> Bool {
        let before: String? = AX.attribute(element, kAXValueAttribute)
        guard AXUIElementSetAttributeValue(element, kAXSelectedTextAttribute as CFString, text as CFString) == .success
        else { return false }
        for _ in 0..<10 {
            let after: String? = AX.attribute(element, kAXValueAttribute)
            if let after, after != before, after.contains(text) { return true }
            usleep(50000)
        }
        return false
    }

    /// The scroll area around an element, if it has a scroll bar Milo can set.
    private static func scrollArea(_ element: AXUIElement) -> AXUIElement? {
        var node: AXUIElement? = element
        for _ in 0..<8 {
            guard let current = node else { return nil }
            if AX.role(current) == kAXScrollAreaRole as String {
                let bars = [kAXVerticalScrollBarAttribute, kAXHorizontalScrollBarAttribute]
                    .compactMap { AX.attribute(current, $0) as AXUIElement? }
                return bars.contains { settable($0, kAXValueAttribute) } ? current : nil
            }
            node = AX.attribute(current, kAXParentAttribute)
        }
        return nil
    }

    /// Moves the scroll bars by about `lines` lines of 16 points each, read back to check.
    private static func scroll(_ area: AXUIElement, lines: (dx: Double, dy: Double)) -> Bool {
        guard let visible = AX.frame(area) else { return false }
        let content = AX.children(area).compactMap(AX.frame).max { $0.width * $0.height < $1.width * $1.height }
        var moved = false
        for (attribute, delta, length, shown) in [
            (kAXVerticalScrollBarAttribute, lines.dy, content?.height ?? 0, visible.height),
            (kAXHorizontalScrollBarAttribute, lines.dx, content?.width ?? 0, visible.width),
        ] where delta != 0 {
            guard let bar: AXUIElement = AX.attribute(area, attribute),
                  let now = (AX.attribute(bar, kAXValueAttribute) as NSNumber?)?.doubleValue else { continue }
            let range = max(length - shown, shown)
            let next = min(1, max(0, now + delta * 16 / range))
            AXUIElementSetAttributeValue(bar, kAXValueAttribute as CFString, NSNumber(value: next))
            let after = (AX.attribute(bar, kAXValueAttribute) as NSNumber?)?.doubleValue
            moved = moved || (after.map { abs($0 - now) > 0.0001 } ?? false)
        }
        return moved
    }

    /// The caret of a text element in global points, for Milo's cursor to show where he types.
    private static func caret(_ element: AXUIElement) -> CGPoint? {
        guard let range: AXValue = AX.attribute(element, kAXSelectedTextRangeAttribute) else { return nil }
        var bounds: CFTypeRef?
        guard AXUIElementCopyParameterizedAttributeValue(element, kAXBoundsForRangeParameterizedAttribute as CFString,
                                                         range, &bounds) == .success,
              let bounds, CFGetTypeID(bounds) == AXValueGetTypeID() else { return nil }
        var rect = CGRect.zero
        AXValueGetValue(bounds as! AXValue, .cgRect, &rect)
        return rect.isEmpty && rect.origin == .zero ? nil : CGPoint(x: rect.minX, y: rect.midY)
    }

    private static func window(of element: AXUIElement) -> AXUIElement? {
        if AX.role(element) == kAXWindowRole as String { return element }
        return AX.attribute(element, kAXWindowAttribute)
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
