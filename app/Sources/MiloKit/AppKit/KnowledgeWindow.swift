import AppKit
import SwiftUI

/// The "What Milo knows" window, opened from the menu bar. Closing only hides it.
public final class KnowledgeWindow: NSWindow {
    private let controller: MiloController

    public init(controller: MiloController) {
        self.controller = controller
        super.init(contentRect: NSRect(x: 0, y: 0, width: 440, height: 520),
                   styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: true)
        title = "What Milo knows"
        titlebarAppearsTransparent = true
        backgroundColor = WindowColors.paperColor
        isReleasedWhenClosed = false
        minSize = NSSize(width: 340, height: 280)
        contentView = NSHostingView(rootView: KnowledgeView(
            knowledge: controller.knowledge,
            forget: { [weak controller] id in controller?.forgetFact(id: id) },
            edit: { [weak controller] id, text in controller?.editFact(id: id, text: text) }))
        if !setFrameUsingName(Self.frameName) { center() }
        setFrameAutosaveName(Self.frameName)
    }

    private static let frameName = "MiloKnowledgeWindow"

    /// Ask the brain for the facts and bring the window to the front.
    public func show() {
        controller.requestFacts()
        // An accessory app has to activate itself before its window can take typing.
        NSApp.activate(ignoringOtherApps: true)
        makeKeyAndOrderFront(nil)
    }
}
