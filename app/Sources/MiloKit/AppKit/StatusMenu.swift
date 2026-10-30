import AppKit

/// The menu bar item.
public final class StatusMenu: NSObject {
    private let controller: MiloController
    private let panel: OverlayPanel
    private let window: ConversationWindow
    private let paths: MiloPaths
    private let statusItem: NSStatusItem
    private let hintItem: NSMenuItem
    private var muteItem: NSMenuItem!

    public init(controller: MiloController, panel: OverlayPanel, window: ConversationWindow, paths: MiloPaths) {
        self.controller = controller
        self.panel = panel
        self.window = window
        self.paths = paths
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        hintItem = NSMenuItem(title: controller.bindings.hint, action: nil, keyEquivalent: "")
        super.init()

        statusItem.button?.image = NSImage(systemSymbolName: "face.smiling", accessibilityDescription: "Milo")
        let menu = NSMenu()
        hintItem.isEnabled = false
        menu.addItem(hintItem)
        menu.addItem(.separator())
        add(menu, "Open conversation", #selector(toggleWindow))
        add(menu, "What's this?", #selector(whatsThis))
        muteItem = add(menu, "Mute proactive nudges", #selector(toggleMute))
        add(menu, "Show / hide Milo", #selector(toggleVisible))
        add(menu, "Move Milo back to the corner", #selector(resetPosition))
        menu.addItem(.separator())
        add(menu, "Open Milo folder", #selector(openHome))
        add(menu, "Open brain log", #selector(openLog))
        add(menu, "Restart brain", #selector(restartBrain))
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Milo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        statusItem.menu = menu
    }

    /// Updates the "Hold … to dictate" line.
    public func show(_ bindings: HotkeyBindings) {
        hintItem.title = bindings.hint
    }

    @discardableResult
    private func add(_ menu: NSMenu, _ title: String, _ action: Selector) -> NSMenuItem {
        let item = menu.addItem(withTitle: title, action: action, keyEquivalent: "")
        item.target = self
        return item
    }

    @objc private func toggleMute() {
        controller.toggleMute()
        muteItem.state = controller.muted ? .on : .off
    }

    @objc private func toggleVisible() { panel.toggleVisible() }
    @objc private func toggleWindow() { window.toggle() }
    @objc private func whatsThis() { controller.screen?.whatsThis() }
    @objc private func resetPosition() { panel.placeBottomRight() }
    @objc private func openHome() { NSWorkspace.shared.open(paths.home) }
    @objc private func openLog() { NSWorkspace.shared.open(paths.brainLog) }
    @objc private func restartBrain() { controller.restartBrain() }
}
