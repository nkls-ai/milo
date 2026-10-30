import AppKit

/// Frontmost app from NSWorkspace, idle time from CGEventSource.
public final class WorkspaceContextProvider: ContextProvider {
    public var onAppSwitch: (() -> Void)?
    private let workspace: NSWorkspace
    private var observer: NSObjectProtocol?

    public init(workspace: NSWorkspace = .shared) {
        self.workspace = workspace
        observer = workspace.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.onAppSwitch?() }
    }

    deinit {
        if let observer { workspace.notificationCenter.removeObserver(observer) }
    }

    public func current() -> AppContext {
        let app = workspace.frontmostApplication?.localizedName ?? ""
        let anyInput = CGEventType(rawValue: ~0)!
        let idle = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: anyInput)
        return AppContext(app: app, idleSeconds: idle)
    }
}
