import AppKit
import Combine

/// The menu bar item.
public final class StatusMenu: NSObject, NSMenuDelegate {
    /// The "Dictation style" choices, in menu order, with plain names.
    static let dictationStyles: [(DictationStyle, String)] = [
        (.preview, "Show the words, paste when I let go"),
        (.type, "Type as I speak"),
        (.off, "Paste when I let go, show nothing"),
    ]

    private let controller: MiloController
    private let panel: OverlayPanel
    private let window: ConversationWindow
    private let settings: SettingsWindow
    private let setup: SetupWindow
    private let paths: MiloPaths
    private let statusItem: NSStatusItem
    private let hintItem: NSMenuItem
    private var muteItem: NSMenuItem!
    private var visibleItem: NSMenuItem!
    private lazy var knowledge = KnowledgeWindow(controller: controller)
    private var styleMenu: NSMenu!
    private var restyle: AnyCancellable?
    private var notesItem: NSMenuItem?
    /// Milo by message: hidden while messages are off.
    private var remoteItems: [NSMenuItem] = []
    private var remoteStatusItem: NSMenuItem!
    private var remotePauseItem: NSMenuItem!
    private var remoteForgetItem: NSMenuItem!

    public init(controller: MiloController, panel: OverlayPanel, window: ConversationWindow, settings: SettingsWindow,
                setup: SetupWindow, paths: MiloPaths) {
        self.controller = controller
        self.panel = panel
        self.window = window
        self.settings = settings
        self.setup = setup
        self.paths = paths
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        hintItem = NSMenuItem(title: controller.bindings.hint, action: nil, keyEquivalent: "")
        super.init()

        // Milo's silhouette, drawn like every menu bar icon (it follows the menu bar's colour),
        // and a red dot instead while he records a meeting.
        restyle = controller.model.$character.combineLatest(controller.model.$recording.removeDuplicates())
            .sink { [weak self] style, recording in self?.showIcon(style, recording: recording) }
        let menu = NSMenu()
        hintItem.isEnabled = false
        menu.addItem(hintItem)
        menu.addItem(.separator())
        add(menu, "Open conversation", #selector(toggleWindow))
        add(menu, "What's this?", #selector(whatsThis))
        add(menu, "What Milo knows…", #selector(showKnowledge))
        if controller.meetings != nil {
            notesItem = add(menu, "Take meeting notes", #selector(toggleNotes))
        }
        muteItem = add(menu, "Pause nudges", #selector(toggleMute))
        muteItem.toolTip = "Milo stops bringing things up by himself. He still answers when you ask."
        visibleItem = add(menu, "Hide Milo", #selector(toggleVisible))
        add(menu, "Move Milo back to the corner", #selector(resetPosition))
        styleMenu = NSMenu()
        styleMenu.delegate = self
        styleMenu.autoenablesItems = false
        for (style, title) in Self.dictationStyles {
            add(styleMenu, title, #selector(pickDictationStyle(_:))).representedObject = style.rawValue
        }
        menu.addItem(withTitle: "Dictation style", action: nil, keyEquivalent: "").submenu = styleMenu
        let remoteSeparator = NSMenuItem.separator()
        menu.addItem(remoteSeparator)
        remoteStatusItem = menu.addItem(withTitle: "", action: nil, keyEquivalent: "")
        remoteStatusItem.isEnabled = false
        remotePauseItem = add(menu, "Pause messages from your phone", #selector(toggleRemotePause))
        remoteForgetItem = add(menu, "Disconnect phone…", #selector(forgetPhone))
        remoteItems = [remoteSeparator, remoteStatusItem, remotePauseItem, remoteForgetItem]
        menu.addItem(.separator())
        add(menu, "Settings…", #selector(openSettings))
        add(menu, "Check permissions…", #selector(openSetup))
        // For whoever set Milo up: out of the way of everyone else.
        let troubleshoot = NSMenu()
        add(troubleshoot, "Restart Milo's brain", #selector(restartBrain))
        add(troubleshoot, "Open the brain log", #selector(openLog))
        add(troubleshoot, "Open Milo's folder", #selector(openHome))
        menu.addItem(withTitle: "Troubleshoot", action: nil, keyEquivalent: "").submenu = troubleshoot
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Milo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        menu.delegate = self
        statusItem.menu = menu
        menuNeedsUpdate(menu)
    }

    /// Shows Milo by message as the brain last reported it, each time the menu opens.
    private func updateRemoteItems() {
        let remote = controller.model.remote
        remoteItems.forEach { $0.isHidden = remote == nil }
        guard let remote else { return }
        remoteStatusItem.title = remote.summary
        remoteStatusItem.toolTip = remote.state == .paired ? nil : remote.detail
        remotePauseItem.state = remote.paused ? .on : .off
        remotePauseItem.isEnabled = remote.state == .paired
        remoteForgetItem.isHidden = remote.state != .paired
    }

    private func showIcon(_ style: CharacterStyle, recording: Bool) {
        notesItem?.title = recording ? "Stop taking notes" : "Take meeting notes"
        guard let button = statusItem.button else { return }
        if recording {
            let config = NSImage.SymbolConfiguration(paletteColors: [.white, .systemRed])
            let image = NSImage(systemSymbolName: "record.circle.fill", accessibilityDescription: "Milo is taking notes")?
                .withSymbolConfiguration(config)
            image?.isTemplate = false
            button.image = image
        } else {
            button.image = WrenIcon.menuBar
        }
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

    /// Each time a menu opens: ticks the dictation style the brain uses in the submenu, and shows Milo by
    /// message as the brain last reported it in the main menu.
    public func menuNeedsUpdate(_ menu: NSMenu) {
        guard menu === styleMenu else {
            visibleItem.title = panel.isVisible ? "Hide Milo" : "Show Milo"
            return updateRemoteItems()
        }
        for item in menu.items {
            item.state = item.representedObject as? String == controller.dictationStyle?.rawValue ? .on : .off
            item.isEnabled = controller.dictationStyle != nil  // no brain yet: nothing to switch
        }
    }

    @objc private func pickDictationStyle(_ item: NSMenuItem) {
        guard let raw = item.representedObject as? String, let style = DictationStyle(rawValue: raw) else { return }
        controller.setDictationStyle(style)
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
    @objc private func openSettings() { settings.open() }
    @objc private func openSetup() { setup.open() }
    @objc private func whatsThis() { controller.screen?.whatsThis() }
    @objc private func showKnowledge() { knowledge.show() }
    @objc private func toggleNotes() { controller.meetings?.toggle() }
    @objc private func resetPosition() { panel.placeBottomRight() }
    @objc private func openHome() { NSWorkspace.shared.open(paths.home) }
    @objc private func openLog() { NSWorkspace.shared.open(paths.brainLog) }
    @objc private func restartBrain() { controller.restartBrain() }
}
