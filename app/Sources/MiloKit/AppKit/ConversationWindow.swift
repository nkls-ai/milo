import AppKit
import Combine
import SwiftUI

/// The Milo window: Today, the conversations and their tasks, and a field to type to him. Closing only hides it.
public final class ConversationWindow: NSWindow {
    private let controller: MiloController
    private let settings: ConversationSettings
    private let route = WindowRoute(page: .live)
    /// The gear in the title bar: open the Settings window.
    public var onSettings: (() -> Void)?

    public init(controller: MiloController) {
        self.controller = controller
        settings = ConversationSettings(talkKey: controller.bindings.talk.displayName)
        super.init(contentRect: NSRect(x: 0, y: 0, width: 780, height: 580),
                   styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: true)
        title = "Milo"
        titlebarAppearsTransparent = true
        isReleasedWhenClosed = false
        minSize = NSSize(width: 320, height: 300)
        contentView = NSHostingView(rootView: ConversationView(
            transcript: controller.transcript, model: controller.model, settings: settings, route: route,
            actions: controller.windowActions, usage: controller.usage)
            .themed(by: controller.model))
        // The title bar shows the window's own colour: keep it Milo's paper.
        backgroundColor = Theme.milo.appKit.tint
        addSettingsButton()
        if !setFrameUsingName(Self.frameName) { placeNearMilo() }
        setFrameAutosaveName(Self.frameName)
    }

    /// A new name for the wider window with its sidebar, so the old narrow frame doesn't come back.
    private static let frameName = "MiloConversationWindow2"

    /// Updates the key named in the empty state.
    public func show(_ bindings: HotkeyBindings) {
        settings.talkKey = bindings.talk.displayName
    }

    /// Show it with the task of helper `id` in view.
    public func show(helper id: String) {
        if !isVisible {
            controller.requestHistory()
            NSApp.activate(ignoringOtherApps: true)
            makeKeyAndOrderFront(nil)
        }
        settings.focus = nil
        settings.focus = id
    }

    /// Show it with meeting `id`'s page: the live transcript while it goes on, the notes once they're written.
    public func show(meeting id: String) {
        let meeting = controller.model.meeting
        let conversation = [meeting.status.id == id ? meeting.status.conversation : "",
                            meeting.notes[id]?.conversation ?? "",
                            controller.transcript.conversations.first { $0.source == "meeting:\(id)" }?.id ?? ""]
            .first { !$0.isEmpty }
        if !isVisible {
            controller.requestHistory()
            NSApp.activate(ignoringOtherApps: true)
            makeKeyAndOrderFront(nil)
        } else {
            NSApp.activate(ignoringOtherApps: true)
            makeKeyAndOrderFront(nil)
        }
        meeting.request(id)
        guard let conversation else { return }
        controller.windowActions.open(conversation)
        route.go(.conversation(conversation))
    }

    /// Show it at Today, where Milo's own reminders are.
    public func showToday() {
        if !isVisible { controller.requestHistory() }
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
        route.go(.today)
    }

    /// Show it at the conversation going on, where text Milo wrote waits to be copied.
    public func showConversation() {
        if !isVisible { controller.requestHistory() }
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
        route.go(.live)
    }

    /// Show it, or hide it if it is open.
    public func toggle() {
        if isVisible {
            orderOut(nil)
            return
        }
        controller.requestHistory()
        // An accessory app has to activate itself before its window can take typing.
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
    }

    private func addSettingsButton() {
        let button = NSButton(image: NSImage(systemSymbolName: "gearshape", accessibilityDescription: "Settings")!,
                              target: self, action: #selector(openSettings))
        button.bezelStyle = .accessoryBarAction
        button.isBordered = false
        button.contentTintColor = .secondaryLabelColor
        button.toolTip = "Settings"
        button.frame = NSRect(x: 0, y: 0, width: 34, height: 24)
        let accessory = NSTitlebarAccessoryViewController()
        accessory.view = button
        accessory.layoutAttribute = .trailing
        addTitlebarAccessoryViewController(accessory)
    }

    @objc private func openSettings() { onSettings?() }

    /// First open: just left of Milo's corner.
    private func placeNearMilo() {
        guard let screen = NSScreen.main else { return center() }
        let f = screen.visibleFrame
        setFrameOrigin(NSPoint(x: f.maxX - OverlayPanel.size.width - frame.width, y: f.minY + 16))
    }
}
