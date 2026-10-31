import AppKit
import Combine
import SwiftUI

/// The setup window. Opens by itself when Milo lacks a permission he needs, and from the menu bar.
/// Checks the permissions once a second only while it is open.
public final class SetupWindow: NSWindow, NSWindowDelegate {
    public let setup: SetupModel
    private let model: MiloModel
    private var helper: NSPanel?
    private var watching: Set<AnyCancellable> = []
    private var apps: ControlledApps?
    private var access: AccessSource?

    public init(setup: SetupModel, model: MiloModel, apps: ControlledApps? = nil, access: AccessSource? = nil) {
        self.setup = setup
        self.model = model
        super.init(contentRect: NSRect(x: 0, y: 0, width: 560, height: 820),
                   styleMask: [.titled, .closable, .resizable, .fullSizeContentView], backing: .buffered, defer: true)
        title = "Set up Milo"
        titlebarAppearsTransparent = true
        isReleasedWhenClosed = false
        delegate = self
        contentView = NSHostingView(rootView: SetupView(setup: setup, apps: apps,
                                                        openAutomation: { access?.openSettings(.control, app: nil) },
                                                        done: { [weak self] in self?.close() })
            .themed(by: model))
        self.apps = apps
        self.access = access
        center()
        setup.restart = { Relaunch.now() }
        model.$state.sink { [weak setup] in setup?.noticed($0) }.store(in: &watching)
        backgroundColor = Theme.milo.appKit.tint
        setup.$helper.sink { [weak self] in self?.showHelper($0 != nil) }.store(in: &watching)
    }

    /// Opens the window if a permission Milo needs is missing.
    public func openIfNeeded() {
        setup.refresh()
        if setup.needsAttention { open() }
    }

    public func open() {
        setup.startWatching()
        if let apps, let access { apps.refresh(from: access) }
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
    }

    public func windowWillClose(_ notification: Notification) {
        setup.stopWatching()
    }

    /// The tile to drag into System Settings, floating at the right edge of the screen where System Settings
    /// (which opens in the middle) leaves room.
    private func showHelper(_ show: Bool) {
        guard show else {
            helper?.orderOut(nil)
            return
        }
        let panel = helper ?? makeHelper()
        helper = panel
        if let screen = NSScreen.main {
            let f = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: f.maxX - panel.frame.width - 24, y: f.midY - panel.frame.height / 2))
        }
        panel.orderFrontRegardless()
    }

    private func makeHelper() -> NSPanel {
        let url = Bundle.main.bundleURL
        let view = DragHelperView(appURL: url, icon: NSWorkspace.shared.icon(forFile: url.path),
                                  close: { [weak self] in self?.setup.closeHelper() })
            .themed(by: model)
        let host = NSHostingView(rootView: view)
        host.layoutSubtreeIfNeeded()
        let panel = NSPanel(contentRect: NSRect(origin: .zero, size: host.fittingSize),
                            styleMask: [.titled, .closable, .utilityWindow, .nonactivatingPanel, .fullSizeContentView],
                            backing: .buffered, defer: false)
        panel.title = "Milo"
        panel.titlebarAppearsTransparent = true
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.isReleasedWhenClosed = false
        panel.contentView = host
        return panel
    }
}

/// Quits Milo and opens him again, e.g. so macOS counts a Screen Recording switch.
public enum Relaunch {
    public static func now() {
        let open = Process()
        open.executableURL = URL(fileURLWithPath: "/bin/sh")
        // Wait for this instance to quit, so the new one isn't turned away as a second copy.
        open.arguments = ["-c", "while kill -0 \(ProcessInfo.processInfo.processIdentifier) 2>/dev/null; do sleep 0.2; done; open \"$0\"",
                          Bundle.main.bundlePath]
        try? open.run()
        NSApp.terminate(nil)
    }
}
