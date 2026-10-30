import AppKit
import Combine
import SwiftUI

/// The setup window. Opens by itself when Milo lacks a permission he needs, and from the menu bar.
/// Checks the permissions once a second only while it is open.
public final class SetupWindow: NSWindow, NSWindowDelegate {
    public let setup: SetupModel
    private var watching: AnyCancellable?

    public init(setup: SetupModel, model: MiloModel) {
        self.setup = setup
        super.init(contentRect: NSRect(x: 0, y: 0, width: 520, height: 780),
                   styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: true)
        title = "Set up Milo"
        isReleasedWhenClosed = false
        delegate = self
        contentView = NSHostingView(rootView: SetupView(setup: setup, done: { [weak self] in self?.close() }))
        center()
        watching = model.$state.sink { [weak setup] in setup?.noticed($0) }
    }

    /// Opens the window if a permission Milo needs is missing.
    public func openIfNeeded() {
        setup.refresh()
        if setup.needsAttention { open() }
    }

    public func open() {
        setup.startWatching()
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
    }

    public func windowWillClose(_ notification: Notification) {
        setup.stopWatching()
    }
}
