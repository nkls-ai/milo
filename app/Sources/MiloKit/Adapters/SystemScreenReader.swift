import AppKit

/// Reads the window in front of the user: app, window title, focused element, selection, visible text
/// (Accessibility), and a downscaled screenshot of the window (ScreenCaptureKit). Without a permission it
/// returns what it could read and says in `error` which switch to turn on.
public final class SystemScreenReader: ScreenReader {
    private let shots: ScreenShots
    private let queue = DispatchQueue(label: "milo.screen.read")
    private let apps: FrontApps

    public convenience init(screensFolder: URL) {
        self.init(shots: ScreenShots(folder: screensFolder), apps: FrontApps())
    }

    init(shots: ScreenShots, apps: FrontApps) {
        self.shots = shots
        self.apps = apps
    }

    public func capture(selection: Bool, completion: @escaping (ScreenCapture) -> Void) {
        let front = apps.front()
        if AX.isSecret(front) {
            return completion(ScreenCapture(app: front?.localizedName ?? "", error: AX.secretRefused))
        }
        queue.async { [shots] in
            var capture = ScreenCapture(app: front?.localizedName ?? "")
            var errors: [String] = []
            var frame: CGRect?
            if !AXIsProcessTrusted() {
                errors.append(AX.notTrusted)
            } else if let front {
                let app = AX.application(front.processIdentifier)
                let window = AX.window(of: app)
                frame = window.flatMap(AX.frame)
                capture.window = window.flatMap { AX.string($0, kAXTitleAttribute) } ?? ""
                if let focused: AXUIElement = AX.attribute(app, kAXFocusedUIElementAttribute) {
                    capture.focused = Self.describe(focused)
                    if !AX.isSecure(focused), let selected = AX.string(focused, kAXSelectedTextAttribute) {
                        capture.selection = String(selected.prefix(8000))
                    }
                }
                if selection && !capture.selection.isEmpty {
                    return DispatchQueue.main.async { completion(capture) }  // the selection is enough
                }
                if let window { capture.text = AX.text(of: window) }
            }
            guard let pid = front?.processIdentifier else {
                capture.error = (errors + ["No app is in front."]).joined(separator: " ")
                return DispatchQueue.main.async { completion(capture) }
            }
            Task {
                do {
                    capture.image = try await shots.window(pid: pid, near: frame).url.path
                } catch let failure as ScreenShots.Failure {
                    errors.append(failure.message)
                } catch {
                    errors.append(ScreenShots.Failure.failed(error.localizedDescription).message)
                }
                capture.error = errors.joined(separator: " ")
                DispatchQueue.main.async { completion(capture) }
            }
        }
    }

    /// "text field “To”", "cell “C4” = 1,284".
    static func describe(_ element: AXUIElement) -> String {
        let label = AX.label(element)
        var text = AX.roleName(element)
        if !label.isEmpty { text += " “\(label)”" }
        if !AX.isSecure(element), let value: String = AX.attribute(element, kAXValueAttribute),
           !value.isEmpty, value != label {
            text += " = \(AX.clip(value, 200))"
        }
        return text
    }
}

/// The app the user works in. When Milo's own window is in front (the user just clicked it), that's the
/// app that was in front before.
final class FrontApps {
    private var last: NSRunningApplication?
    private var observer: NSObjectProtocol?

    init() {
        last = Self.other(NSWorkspace.shared.frontmostApplication)
        observer = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
        ) { [weak self] note in
            let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
            if let app = Self.other(app) { self?.last = app }
        }
    }

    deinit {
        if let observer { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
    }

    func front() -> NSRunningApplication? {
        Self.other(NSWorkspace.shared.frontmostApplication) ?? last
    }

    /// The app unless it is Milo.
    private static func other(_ app: NSRunningApplication?) -> NSRunningApplication? {
        app?.processIdentifier == getpid() ? nil : app
    }
}
