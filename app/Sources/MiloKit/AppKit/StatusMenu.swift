import AppKit

/// The menu bar item.
public final class StatusMenu: NSObject, NSMenuDelegate {
    private let controller: MiloController
    private let panel: OverlayPanel
    private let window: ConversationWindow
    private let paths: MiloPaths
    private let statusItem: NSStatusItem
    private let hintItem: NSMenuItem
    private var muteItem: NSMenuItem!
    /// Milo by message: hidden while messages are off.
    private var remoteItems: [NSMenuItem] = []
    private var remoteStatusItem: NSMenuItem!
    private var remotePauseItem: NSMenuItem!
    private var remoteForgetItem: NSMenuItem!

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
        let remoteSeparator = NSMenuItem.separator()
        menu.addItem(remoteSeparator)
        remoteStatusItem = menu.addItem(withTitle: "", action: nil, keyEquivalent: "")
        remoteStatusItem.isEnabled = false
        remotePauseItem = add(menu, "Pause messages from your phone", #selector(toggleRemotePause))
        remoteForgetItem = add(menu, "Disconnect phone…", #selector(forgetPhone))
        remoteItems = [remoteSeparator, remoteStatusItem, remotePauseItem, remoteForgetItem]
        menu.addItem(.separator())
        add(menu, "Open Milo folder", #selector(openHome))
        add(menu, "Open brain log", #selector(openLog))
        add(menu, "Restart brain", #selector(restartBrain))
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Milo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.delegate = self
        statusItem.menu = menu
        menuNeedsUpdate(menu)
    }

    /// Shows Milo by message as the brain last reported it, each time the menu opens.
    public func menuNeedsUpdate(_ menu: NSMenu) {
        let remote = controller.model.remote
        remoteItems.forEach { $0.isHidden = remote == nil }
        guard let remote else { return }
        remoteStatusItem.title = remote.summary
        remoteStatusItem.toolTip = remote.state == .paired ? nil : remote.detail
        remotePauseItem.state = remote.paused ? .on : .off
        remotePauseItem.isEnabled = remote.state == .paired
        remoteForgetItem.isHidden = remote.state != .paired
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

    @objc private func toggleRemotePause() {
        guard let remote = controller.model.remote else { return }
        controller.setRemotePaused(!remote.paused)
    }

    @objc private func forgetPhone() {
        guard let remote = controller.model.remote else { return }
        let alert = NSAlert()
        alert.messageText = "Disconnect your phone from Milo?"
        alert.informativeText = "Milo stops answering that \(remote.label) chat. To connect again, message Milo "
            + "and send the new code he shows here."
        alert.addButton(withTitle: "Disconnect")
        alert.addButton(withTitle: "Cancel")
        if alert.runModal() == .alertFirstButtonReturn { controller.forgetPhone() }
    }

    @objc private func toggleVisible() { panel.toggleVisible() }
    @objc private func toggleWindow() { window.toggle() }
    @objc private func whatsThis() { controller.screen?.whatsThis() }
    @objc private func resetPosition() { panel.placeBottomRight() }
    @objc private func openHome() { NSWorkspace.shared.open(paths.home) }
    @objc private func openLog() { NSWorkspace.shared.open(paths.brainLog) }
    @objc private func restartBrain() { controller.restartBrain() }
}
