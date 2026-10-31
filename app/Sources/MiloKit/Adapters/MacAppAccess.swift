import AppKit
import Contacts
import CoreGraphics
import Security

/// AccessSource on macOS (ADR 25): Automation per app through `AEDeterminePermissionToAutomateTarget`, which can
/// ask the user once and otherwise answers at once; Accessibility and Screen Recording as the setup window checks
/// them; Contacts, which macOS asks about once (ADR 39); and where a sandboxed app may save without macOS asking,
/// from its signed entitlements.
public final class MacAppAccess: AccessSource {
    /// The button in macOS's Automation question that says yes.
    static let allowButton = "Allow"
    /// How long `launch` waits for an app that isn't running yet.
    static let launchWait: TimeInterval = 10
    private let home: String
    private let lock = NSLock()
    private var placesCache: [String: [String]?] = [:]

    public init(home: String = NSHomeDirectory()) {
        self.home = home
    }

    public func check(_ need: AccessNeed, app: AccessApp?, launch: Bool) -> AccessAnswer {
        switch need {
        case .ui: AccessAnswer(AXIsProcessTrusted() ? .yes : .no, system: "macOS", label: "Accessibility")
        case .screen: AccessAnswer(CGPreflightScreenCaptureAccess() ? .yes : .no, system: "macOS", label: "Screen Recording")
        case .control: control(app, ask: false, launch: launch)
        case .contacts: AccessAnswer(Self.contacts(), system: "macOS", label: "Contacts")
        }
    }

    public func request(_ need: AccessNeed, app: AccessApp?) -> AccessAnswer {
        // Accessibility and Screen Recording are switched on in System Settings, from the permissions window that
        // Fix it opens; nothing here pops up a dialog for them. Contacts has macOS's own question, once.
        switch need {
        case .control: return control(app, ask: true, launch: true)
        case .contacts:
            guard Self.contacts() == .ask else { return check(need, app: app, launch: false) }
            let answered = DispatchSemaphore(value: 0)
            CNContactStore().requestAccess(for: .contacts) { _, _ in answered.signal() }
            answered.wait()
            return check(need, app: app, launch: false)
        default: return check(need, app: app, launch: false)
        }
    }

    public func places(for app: AccessApp) -> [String]? {
        let key = app.bundle.isEmpty ? app.name.lowercased() : app.bundle.lowercased()
        lock.lock()
        if let cached = placesCache[key] { lock.unlock(); return cached }
        lock.unlock()
        let found = locate(app).flatMap { Self.sandboxPlaces(at: $0.url, bundle: $0.app.bundle, home: home) }
        lock.lock()
        placesCache[key] = .some(found)
        lock.unlock()
        return found
    }

    public func openSettings(_ need: AccessNeed, app: AccessApp?) {
        let page = switch need {
        case .control: "Privacy_Automation"
        case .ui: "Privacy_Accessibility"
        case .screen: "Privacy_ScreenCapture"
        case .contacts: "Privacy_Contacts"
        }
        // There is no link to one app's row: the page lists Milo with a switch per app under him.
        guard let url = URL(string: "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?\(page)") else { return }
        NSWorkspace.shared.open(url)
    }

    // MARK: Contacts

    static func contacts() -> AccessState {
        switch CNContactStore.authorizationStatus(for: .contacts) {
        case .authorized: .yes
        case .notDetermined: .ask
        case .denied, .restricted: .no
        @unknown default: .yes  // newer kinds of access (limited) still read the contacts the user picked
        }
    }

    // MARK: Automation

    private func control(_ app: AccessApp?, ask: Bool, launch: Bool) -> AccessAnswer {
        guard let app, let found = locate(app) else {
            return AccessAnswer(.unknown, app: app, system: "macOS")
        }
        let target = found.app
        if launch && Self.runningApp(target.bundle) == nil { Self.start(found.url, bundle: target.bundle) }
        return AccessAnswer(Self.automation(target.bundle, ask: ask), app: target, system: "macOS",
                            button: Self.allowButton)
    }

    /// Whether Milo may send Apple Events to `bundle`. With `ask`, macOS shows its question if it hasn't yet and
    /// this waits for the answer. Only a running app can say; otherwise unknown.
    static func automation(_ bundle: String, ask: Bool) -> AccessState {
        var target = AEAddressDesc()
        let created = bundle.withCString { AECreateDesc(typeApplicationBundleID, $0, strlen($0), &target) }
        guard created == noErr else { return .unknown }
        defer { AEDisposeDesc(&target) }
        switch AEDeterminePermissionToAutomateTarget(&target, typeWildCard, typeWildCard, ask) {
        case noErr: return .yes
        case OSStatus(errAEEventWouldRequireUserConsent): return .ask
        case OSStatus(errAEEventNotPermitted): return .no
        default: return .unknown  // procNotFound: not running
        }
    }

    /// Starts an app without bringing it to the front, and waits until it has finished launching.
    private static func start(_ url: URL, bundle: String) {
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = false
        configuration.addsToRecentItems = false
        NSWorkspace.shared.openApplication(at: url, configuration: configuration) { _, _ in }
        let deadline = Date().addingTimeInterval(launchWait)
        while Date() < deadline {
            if let app = runningApp(bundle), app.isFinishedLaunching { return }
            Thread.sleep(forTimeInterval: 0.1)
        }
    }

    private static func runningApp(_ bundle: String) -> NSRunningApplication? {
        NSRunningApplication.runningApplications(withBundleIdentifier: bundle).first
    }

    // MARK: Finding the app

    /// The app's bundle id and where it is installed, from its bundle id, a running app or the usual folders.
    private func locate(_ app: AccessApp) -> (app: AccessApp, url: URL)? {
        if !app.bundle.isEmpty, let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: app.bundle) {
            return (AccessApp(name: app.name.isEmpty ? Self.name(at: url) : app.name, bundle: app.bundle), url)
        }
        if let running = MacHands.running(app.name), let url = running.bundleURL, let bundle = running.bundleIdentifier {
            return (AccessApp(name: running.localizedName ?? app.name, bundle: bundle), url)
        }
        let file = app.name.hasSuffix(".app") ? app.name : app.name + ".app"
        let folders = ["/Applications", "/System/Applications", "/Applications/Utilities",
                       "/System/Applications/Utilities", home + "/Applications", "/System/Library/CoreServices"]
        for folder in folders {
            let url = URL(fileURLWithPath: folder).appendingPathComponent(file)
            if let bundle = Bundle(url: url)?.bundleIdentifier {
                return (AccessApp(name: app.name, bundle: bundle), url)
            }
        }
        return nil
    }

    private static func name(at url: URL) -> String {
        FileManager.default.displayName(atPath: url.path).replacingOccurrences(of: ".app", with: "")
    }

    // MARK: Sandbox

    /// Where a sandboxed app can write without macOS asking the user: its container, its group containers, and
    /// the folders its entitlements open. nil when it isn't sandboxed (or its signature can't be read).
    static func sandboxPlaces(at url: URL, bundle: String, home: String) -> [String]? {
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(url as CFURL, [], &code) == errSecSuccess, let code else { return nil }
        var info: CFDictionary?
        guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
              let signing = info as? [String: Any],
              let entitlements = signing[kSecCodeInfoEntitlementsDict as String] as? [String: Any] else { return nil }
        return places(entitlements: entitlements, bundle: bundle, home: home)
    }

    /// The pure part of `sandboxPlaces`, for tests.
    static func places(entitlements: [String: Any], bundle: String, home: String) -> [String]? {
        guard entitlements["com.apple.security.app-sandbox"] as? Bool == true, !bundle.isEmpty else { return nil }
        var places = ["\(home)/Library/Containers/\(bundle)/Data"]
        for group in entitlements["com.apple.security.application-groups"] as? [String] ?? [] {
            places.append("\(home)/Library/Group Containers/\(group)")
        }
        if entitlements["com.apple.security.files.downloads.read-write"] as? Bool == true {
            places.append("\(home)/Downloads")
        }
        let exception = "com.apple.security.temporary-exception.files."
        for path in entitlements[exception + "home-relative-path.read-write"] as? [String] ?? [] {
            places.append(home + (path.hasPrefix("/") ? path : "/" + path))
        }
        places += entitlements[exception + "absolute-path.read-write"] as? [String] ?? []
        return places
    }
}
