import AppKit
import SwiftUI

/// The Milo window: the conversation as text and a field to type to him. Closing only hides it.
public final class ConversationWindow: NSWindow {
    private let controller: MiloController
    private let settings: ConversationSettings

    public init(controller: MiloController) {
        self.controller = controller
        settings = ConversationSettings(talkKey: controller.bindings.talk.displayName)
        super.init(contentRect: NSRect(x: 0, y: 0, width: 420, height: 560),
                   styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: true)
        title = "Milo"
        titlebarAppearsTransparent = true
        backgroundColor = WindowColors.paperColor
        isReleasedWhenClosed = false
        minSize = NSSize(width: 320, height: 300)
        contentView = NSHostingView(rootView: ConversationView(
            transcript: controller.transcript, model: controller.model, settings: settings,
            send: { [weak controller] text, speak in controller?.send(text: text, speak: speak) }))
        if !setFrameUsingName(Self.frameName) { placeNearMilo() }
        setFrameAutosaveName(Self.frameName)
    }

    private static let frameName = "MiloConversationWindow"

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

    /// First open: just left of Milo's corner.
    private func placeNearMilo() {
        guard let screen = NSScreen.main else { return center() }
        let f = screen.visibleFrame
        setFrameOrigin(NSPoint(x: f.maxX - OverlayPanel.size.width - frame.width, y: f.minY + 16))
    }
}
