import AppKit
import ApplicationServices

/// Follows a window of another app while Milo works in it, so the outline and Pip track it when the user (or
/// the app) moves, resizes or minimizes it. It listens for the Accessibility notifications on that window,
/// and also polls a few times a second as a fallback for apps that don't post them and to see whether the
/// window is on screen at all (minimized, its app hidden, on another space). Global points, top-left origin.
/// Callbacks on the main queue.
public final class MacWindowWatcher: WindowWatcher {
    private static let notes = [kAXMovedNotification, kAXResizedNotification, kAXWindowMiniaturizedNotification,
                                kAXWindowDeminiaturizedNotification, kAXUIElementDestroyedNotification]
    private var observer: AXObserver?
    private var window: AXUIElement?
    private var app: AXUIElement?
    private var pid: Int32 = 0
    private var changed: ((CGRect?) -> Void)?
    private var poll: Timer?
    private var last: CGRect?
    public private(set) var windowNumber: Int?

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
        self.pid = pid
        windowNumber = Self.number(pid: pid, frame: AX.frame(window) ?? frame)

        var observer: AXObserver?
        let callback: AXObserverCallback = { _, _, _, refcon in
            guard let refcon else { return }
            Unmanaged<MacWindowWatcher>.fromOpaque(refcon).takeUnretainedValue().report()
        }
        if AXObserverCreate(pid, callback, &observer) == .success, let observer {
            self.observer = observer
            let me = Unmanaged.passUnretained(self).toOpaque()
            for note in Self.notes {
                AXObserverAddNotification(observer, window, note as CFString, me)
            }
            CFRunLoopAddSource(CFRunLoopGetMain(), AXObserverGetRunLoopSource(observer), .defaultMode)
        }
        // A light poll catches apps that stay quiet (some Electron windows) and the window closing.
        let timer = Timer(timeInterval: 0.25, repeats: true) { [weak self] _ in self?.report() }
        RunLoop.main.add(timer, forMode: .common)
        poll = timer
    }

    /// Activates the app and raises the window whose frame matches, so it is in front of the user's other windows.
    public func bringForward(pid: Int32, frame: CGRect) {
        if let window = Self.window(of: AX.application(pid), matching: frame) {
            AXUIElementSetAttributeValue(window, kAXMainAttribute as CFString, kCFBooleanTrue)
            AXUIElementPerformAction(window, kAXRaiseAction as CFString)
        }
        NSRunningApplication(processIdentifier: pid)?.activate()
    }

    public func stop() {
        poll?.invalidate()
        poll = nil
        if let observer, let window {
            for note in Self.notes {
                AXObserverRemoveNotification(observer, window, note as CFString)
            }
            CFRunLoopRemoveSource(CFRunLoopGetMain(), AXObserverGetRunLoopSource(observer), .defaultMode)
        }
        observer = nil
        window = nil
        app = nil
        changed = nil
        last = nil
        windowNumber = nil
    }

    /// Reports the frame while the window is on screen and nil while it is away; after it closes, nil and the end.
    private func report() {
        guard let window else { return }
        guard let frame = AX.frame(window) else {
            let changed = changed
            stop()
            if last != nil { changed?(nil) }
            return
        }
        if windowNumber == nil { windowNumber = Self.number(pid: pid, frame: frame) }
        let shown = isShown(window) ? frame : nil
        if shown == last { return }
        last = shown
        changed?(shown)
    }

    /// Not minimized, its app not hidden, and on the current space.
    private func isShown(_ window: AXUIElement) -> Bool {
        if AX.attribute(window, kAXMinimizedAttribute) == true { return false }
        if NSRunningApplication(processIdentifier: pid)?.isHidden == true { return false }
        guard let windowNumber,
              let info = (CGWindowListCreateDescriptionFromArray([CGWindowID(windowNumber)] as CFArray)
                as? [[String: Any]])?.first else { return true }
        return info[kCGWindowIsOnscreen as String] as? Bool ?? false
    }

    /// The window server's number for the window of `pid` at `frame` (top-left global points): the closest of
    /// its normal windows, which bounds and owner show without Screen Recording.
    private static func number(pid: Int32, frame: CGRect) -> Int? {
        guard let list = CGWindowListCopyWindowInfo([.optionAll, .excludeDesktopElements], kCGNullWindowID)
                as? [[String: Any]] else { return nil }
        let candidates = list.compactMap { info -> (Int, CGRect)? in
            guard info[kCGWindowOwnerPID as String] as? Int32 == pid, info[kCGWindowLayer as String] as? Int == 0,
                  let number = info[kCGWindowNumber as String] as? Int,
                  let bounds = info[kCGWindowBounds as String] as? NSDictionary,
                  let rect = CGRect(dictionaryRepresentation: bounds) else { return nil }
            return (number, rect)
        }
        let best = candidates.min { distance($0.1, frame) < distance($1.1, frame) }
        guard let best, distance(best.1, frame) < 12 else { return nil }
        return best.0
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
