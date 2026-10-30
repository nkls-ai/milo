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
    private lazy var knowledge = KnowledgeWindow(controller: controller)
    private var styleMenu: NSMenu!
    private var restyle: AnyCancellable?

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

        // A small sign of the skin he wears, drawn like every menu bar icon (it follows the menu bar's colour).
        restyle = controller.model.$character.sink { [weak self] in
            self?.statusItem.button?.image = NSImage(systemSymbolName: Self.symbol(for: $0), accessibilityDescription: "Milo")
        }
        let menu = NSMenu()
        hintItem.isEnabled = false
        menu.addItem(hintItem)
        menu.addItem(.separator())
        add(menu, "Open conversation", #selector(toggleWindow))
        add(menu, "What's this?", #selector(whatsThis))
        add(menu, "What Milo knows…", #selector(showKnowledge))
        muteItem = add(menu, "Mute proactive nudges", #selector(toggleMute))
        add(menu, "Show / hide Milo", #selector(toggleVisible))
        add(menu, "Move Milo back to the corner", #selector(resetPosition))
        styleMenu = NSMenu()
        styleMenu.delegate = self
        styleMenu.autoenablesItems = false
        for (style, title) in Self.dictationStyles {
            add(styleMenu, title, #selector(pickDictationStyle(_:))).representedObject = style.rawValue
        }
        menu.addItem(withTitle: "Dictation style", action: nil, keyEquivalent: "").submenu = styleMenu
        menu.addItem(.separator())
        add(menu, "Settings…", #selector(openSettings))
        add(menu, "Check permissions…", #selector(openSetup))
        add(menu, "Open Milo folder", #selector(openHome))
        add(menu, "Open brain log", #selector(openLog))
        add(menu, "Restart brain", #selector(restartBrain))
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit Milo", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        statusItem.menu = menu
    }

    static func symbol(for style: CharacterStyle) -> String {
        switch style {
        case .pip: "bird"
        case .classic: "face.smiling"
        case .dragon: "flame"
        case .kit: "pawprint"
        case .glow: "sparkle"
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

    /// Ticks the style the brain uses each time the submenu opens.
    public func menuNeedsUpdate(_ menu: NSMenu) {
        guard menu === styleMenu else { return }
        for item in menu.items {
            item.state = item.representedObject as? String == controller.dictationStyle?.rawValue ? .on : .off
            item.isEnabled = controller.dictationStyle != nil  // no brain yet: nothing to switch
        }
    }

    @objc private func pickDictationStyle(_ item: NSMenuItem) {
        guard let raw = item.representedObject as? String, let style = DictationStyle(rawValue: raw) else { return }
        controller.setDictationStyle(style)
    }

    @objc private func toggleVisible() { panel.toggleVisible() }
    @objc private func toggleWindow() { window.toggle() }
    @objc private func openSettings() { settings.open() }
    @objc private func openSetup() { setup.open() }
    @objc private func whatsThis() { controller.screen?.whatsThis() }
    @objc private func showKnowledge() { knowledge.show() }
    @objc private func resetPosition() { panel.placeBottomRight() }
    @objc private func openHome() { NSWorkspace.shared.open(paths.home) }
    @objc private func openLog() { NSWorkspace.shared.open(paths.brainLog) }
    @objc private func restartBrain() { controller.restartBrain() }
}
