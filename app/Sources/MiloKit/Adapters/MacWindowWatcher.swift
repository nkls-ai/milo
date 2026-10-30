import AppKit
import ApplicationServices

/// Follows a window of another app while Milo works in it, so the outline and Pip track it when the user (or
/// the app) moves or resizes it. It listens for the Accessibility move and resize notifications on that app,
/// and also polls a few times a second as a fallback for apps that don't post them. Global points, top-left
/// origin. Callbacks on the main queue.
public final class MacWindowWatcher: WindowWatcher {
    private var observer: AXObserver?
    private var window: AXUIElement?
    private var app: AXUIElement?
    private var changed: ((CGRect?) -> Void)?
    private var poll: Timer?
    private var last: CGRect?

    public init() {}

    public func watch(pid: Int32, frame: CGRect, changed: @escaping (CGRect?) -> Void) {
        stop()
        self.changed = changed
        last = frame
        let app = AX.application(pid)
        guard let window = Self.window(of: app, matching: frame) else {
            // No handle on it: report the frame once and poll nothing.
            changed(frame)
            return
        }
        self.app = app
        self.window = window

        var observer: AXObserver?
        let callback: AXObserverCallback = { _, _, _, refcon in
            guard let refcon else { return }
            Unmanaged<MacWindowWatcher>.fromOpaque(refcon).takeUnretainedValue().report()
        }
        if AXObserverCreate(pid, callback, &observer) == .success, let observer {
            self.observer = observer
            let me = Unmanaged.passUnretained(self).toOpaque()
            for note in [kAXMovedNotification, kAXResizedNotification, kAXWindowMiniaturizedNotification,
                         kAXUIElementDestroyedNotification] {
                AXObserverAddNotification(observer, window, note as CFString, me)
            }
            CFRunLoopAddSource(CFRunLoopGetMain(), AXObserverGetRunLoopSource(observer), .defaultMode)
        }
        // A light poll catches apps that stay quiet (some Electron windows) and the window closing.
        let timer = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in self?.report() }
        RunLoop.main.add(timer, forMode: .common)
        poll = timer
    }

    public func stop() {
        poll?.invalidate()
        poll = nil
        if let observer, let window {
            for note in [kAXMovedNotification, kAXResizedNotification, kAXWindowMiniaturizedNotification,
                         kAXUIElementDestroyedNotification] {
                AXObserverRemoveNotification(observer, window, note as CFString)
            }
            CFRunLoopRemoveSource(CFRunLoopGetMain(), AXObserverGetRunLoopSource(observer), .defaultMode)
        }
        observer = nil
        window = nil
        app = nil
        changed = nil
        last = nil
    }

    private func report() {
        guard let window else { return }
        let frame = AX.frame(window)
        if frame == last { return }
        last = frame
        changed?(frame)
        if frame == nil { stop() }
    }

    /// The app's window whose Accessibility frame matches `frame`, else its focused or first window.
    private static func window(of app: AXUIElement, matching frame: CGRect) -> AXUIElement? {
        let windows: [AXUIElement] = AX.attribute(app, kAXWindowsAttribute) ?? []
        let match = windows.min { a, b in
            Self.distance(AX.frame(a), frame) < Self.distance(AX.frame(b), frame)
        }
        if let match, Self.distance(AX.frame(match), frame) < 12 { return match }
        return AX.window(of: app)
    }

    private static func distance(_ a: CGRect?, _ b: CGRect) -> CGFloat {
        guard let a else { return .greatestFiniteMagnitude }
        return abs(a.minX - b.minX) + abs(a.minY - b.minY) + abs(a.width - b.width) + abs(a.height - b.height)
    }
}
