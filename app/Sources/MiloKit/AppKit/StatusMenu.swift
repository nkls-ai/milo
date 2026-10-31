import AppKit
import Combine

/// The menu bar item.
public final class StatusMenu: NSObject, NSMenuDelegate, NSMenuItemValidation {
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
    private var watching: AnyCancellable?
    private var notesItem: NSMenuItem?
    /// "Auto mode is on" and its switch: shown only while Milo acts without asking (ADR 22).
    private var autoItems: [NSMenuItem] = []
    /// While a meeting goes on: what it is, Pause, Open, the note for the chat.
    private var meetingItems: [NSMenuItem] = []
    private var meetingTitleItem: NSMenuItem?
    private var meetingPauseItem: NSMenuItem?
    private var meetingWatch: AnyCancellable?
    /// Ticks the time in the menu bar once a second, only while a meeting is noted.
    private var clock: Timer?
    /// Milo by message: hidden while messages are off.
    private var remoteItems: [NSMenuItem] = []
    private var remoteStatusItem: NSMenuItem!
    private var remotePauseItem: NSMenuItem!
    private var remoteForgetItem: NSMenuItem!
    /// "Apps Milo may control": read from `apps` each time it opens; any row opens System Settings (ADR 25).
    private let apps: ControlledApps?
    private let access: AccessSource?
    private var appsMenu: NSMenu?

    public init(controller: MiloController, panel: OverlayPanel, window: ConversationWindow, settings: SettingsWindow,
                setup: SetupWindow, paths: MiloPaths, apps: ControlledApps? = nil, access: AccessSource? = nil) {
        self.apps = apps
        self.access = access
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
        // and a red dot instead while he records a meeting. Auto is the default (ADR 23), so it gets no badge: the
        // menu only says so.
        let auto = controller.settingsModel.$report
            .map { $0?["approvals", "ask"]?.value.string == "auto" }
            .removeDuplicates()
        watching = controller.model.$recording.removeDuplicates().combineLatest(auto)
            .sink { [weak self] recording, auto in self?.showIcon(recording: recording, auto: auto) }
        let menu = NSMenu()
        hintItem.isEnabled = false
        menu.addItem(hintItem)
        let autoStatus = menu.addItem(withTitle: "Auto mode: Milo asks only when it matters", action: nil, keyEquivalent: "")
        autoStatus.isEnabled = false
        autoStatus.toolTip = "He still asks before anything that can't be undone, sending, buying and money, and "
            + "never touches passwords or security settings."
        autoItems = [autoStatus, add(menu, "Turn off auto mode", #selector(endAutoMode))]
        menu.addItem(.separator())
        add(menu, "Open conversation", #selector(toggleWindow))
        add(menu, "What's this?", #selector(whatsThis))
        add(menu, "What Milo knows…", #selector(showKnowledge))
        if controller.meetings != nil {
            let title = menu.addItem(withTitle: "", action: nil, keyEquivalent: "")
            title.isEnabled = false
            meetingTitleItem = title
            notesItem = add(menu, "Take meeting notes", #selector(toggleNotes))
            meetingPauseItem = add(menu, "Pause notes", #selector(togglePause))
            let open = add(menu, "Open the meeting", #selector(openMeeting))
            let consent = add(menu, "Copy a note for the chat", #selector(copyConsent))
            consent.toolTip = "A line telling the others that Milo takes notes, to paste into the call's chat"
            meetingItems = [title, meetingPauseItem!, open, consent]
            meetingWatch = controller.model.meeting.$status.removeDuplicates()
                .sink { [weak self] in self?.showMeeting($0) }
        }
        muteItem = add(menu, "Pause nudges", #selector(toggleMute))
        muteItem.toolTip = "Milo stops bringing things up by himself. He still answers when you ask."
        visibleItem = add(menu, "Hide Milo", #selector(hideMilo))
        visibleItem.toolTip = "Milo leaves the screen until you press a key or he has something for you."
        visibleItem.setAccessibilityHelp(visibleItem.toolTip)
        add(menu, "Move Milo back to the corner", #selector(resetPosition))
        styleMenu = NSMenu()
        styleMenu.delegate = self
        styleMenu.autoenablesItems = false
        for (style, title) in Self.dictationStyles {
            add(styleMenu, title, #selector(pickDictationStyle(_:))).representedObject = style.rawValue
        }
        menu.addItem(withTitle: "Dictation style", action: nil, keyEquivalent: "").submenu = styleMenu
        add(menu, "Dictation words…", #selector(openDictionary)).toolTip =
            "The words Milo learned from your fixes. Change or delete any line."
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
        if apps != nil {
            let list = NSMenu()
            list.delegate = self
            list.autoenablesItems = false
            appsMenu = list
            menu.addItem(withTitle: "Apps Milo may control", action: nil, keyEquivalent: "").submenu = list
        }
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

    private func showIcon(recording: Bool, auto: Bool) {
        notesItem?.title = recording ? "Stop taking notes" : "Take meeting notes"
        autoItems.forEach { $0.isHidden = !auto }
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

    /// The meeting in the menu bar: the time next to the red dot while it records, and its items in the menu.
    private func showMeeting(_ status: MeetingStatus) {
        meetingItems.forEach { $0.isHidden = !status.live }
        meetingPauseItem?.title = status.phase == .paused ? "Go on taking notes" : "Pause notes"
        clock?.invalidate()
        clock = nil
        if status.live {
            let timer = Timer(timeInterval: 1, repeats: true) { [weak self] _ in self?.tick() }
            RunLoop.main.add(timer, forMode: .common)
            clock = timer
        }
        tick()
    }

    private func tick() {
        let meeting = controller.model.meeting
        let status = meeting.status
        let time = MeetingModel.clock(meeting.elapsed())
        meetingTitleItem?.title = status.phase == .paused ? "Notes paused at \(time)" : "Taking notes · \(time)"
        guard let button = statusItem.button else { return }
        if status.live {
            statusItem.length = NSStatusItem.variableLength
            button.imagePosition = .imageLeading
            button.title = " " + time
            button.font = .monospacedDigitSystemFont(ofSize: NSFont.systemFontSize - 1, weight: .medium)
            button.setAccessibilityLabel(status.phase == .paused ? "Milo's notes are paused" : "Milo is taking notes, \(time)")
        } else {
            button.title = ""
            statusItem.length = NSStatusItem.squareLength
            button.setAccessibilityLabel(nil)
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
        if menu === appsMenu { return updateApps(menu) }
        guard menu === styleMenu else { return updateRemoteItems() }
        for item in menu.items {
            item.state = item.representedObject as? String == controller.dictationStyle?.rawValue ? .on : .off
            item.isEnabled = controller.dictationStyle != nil  // no brain yet: nothing to switch
        }
    }

    /// The rows of "Apps Milo may control": each app macOS was asked about, ticked when allowed.
    static func appRows(_ entries: [ControlledApps.Entry]) -> [(title: String, allowed: Bool)] {
        entries.map { ($0.allowed ? $0.app.label : "\($0.app.label): not allowed", $0.allowed) }
    }

    private func updateApps(_ menu: NSMenu) {
        guard let apps else { return }
        if let access { apps.refresh(from: access) }  // a switch flipped in System Settings shows next time
        menu.removeAllItems()
        let rows = Self.appRows(apps.entries)
        if rows.isEmpty {
            let none = menu.addItem(withTitle: "None yet. macOS asks the first time Milo needs an app.", action: nil,
                                    keyEquivalent: "")
            none.isEnabled = false
        }
        for row in rows {
            let item = add(menu, row.title, #selector(openAutomation))
            item.state = row.allowed ? .on : .off
            item.toolTip = "Switch it on or off in System Settings › Privacy & Security › Automation, under Milo."
        }
        menu.addItem(.separator())
        add(menu, "Change in System Settings…", #selector(openAutomation))
    }

    @objc private func openAutomation() {
        access?.openSettings(.control, app: nil)
    }

    /// A click on the menu bar icon brings Milo back if he left the screen, and his wait starts over.
    public func menuWillOpen(_ menu: NSMenu) {
        guard menu === statusItem.menu else { return }
        controller.model.presence.summon()
    }

    /// "Hide Milo" only while nothing needs him: he never leaves a question, his words or his work.
    public func validateMenuItem(_ item: NSMenuItem) -> Bool {
        item !== visibleItem || controller.model.presence.canLeave
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

    @objc private func hideMilo() { controller.model.presence.dismiss() }
    @objc private func toggleWindow() { window.toggle() }
    @objc private func openSettings() { settings.open() }
    @objc private func endAutoMode() { controller.endAutoMode() }
    @objc private func openSetup() { setup.open() }
    @objc private func whatsThis() { controller.screen?.whatsThis() }
    @objc private func showKnowledge() { knowledge.show() }
    @objc private func toggleNotes() { controller.meetings?.toggle() }
    @objc private func togglePause() { controller.model.meeting.pause(controller.model.meeting.status.phase != .paused) }
    @objc private func openMeeting() { controller.model.meeting.open(controller.model.meeting.status.id) }
    @objc private func copyConsent() { controller.model.meeting.copyConsent() }
    @objc private func resetPosition() {
        panel.placeBottomRight()
        controller.model.presence.summon()
    }
    @objc private func openHome() { NSWorkspace.shared.open(paths.home) }
    @objc private func openDictionary() { Self.openText(paths.dictionary) }

    /// A plain text file in the user's editor for it, or in TextEdit when no app takes that kind of file.
    public static func openText(_ url: URL) {
        if NSWorkspace.shared.urlForApplication(toOpen: url) != nil {
            NSWorkspace.shared.open(url)
        } else if let textEdit = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.apple.TextEdit") {
            NSWorkspace.shared.open([url], withApplicationAt: textEdit, configuration: NSWorkspace.OpenConfiguration())
        }
    }
    @objc private func openLog() { NSWorkspace.shared.open(paths.brainLog) }
    @objc private func restartBrain() { controller.restartBrain() }
}
