import AppKit

/// The application delegate: runs the given closures at launch and termination.
public final class AppLifecycle: NSObject, NSApplicationDelegate {
    private let onLaunch: () -> Void
    private let onTerminate: () -> Void

    public init(onLaunch: @escaping () -> Void, onTerminate: @escaping () -> Void) {
        self.onLaunch = onLaunch
        self.onTerminate = onTerminate
    }

    public func applicationDidFinishLaunching(_ notification: Notification) { onLaunch() }
    public func applicationWillTerminate(_ notification: Notification) { onTerminate() }
}
