import AppKit
import Combine
import SwiftUI

/// A borderless panel that outlines the window Milo works in. It follows `MiloModel.workingWindow` (AppKit
/// coordinates), shows above everything on every space, and lets clicks through except on its Stop button.
/// When the real mouse and keyboard are borrowed (`handsBorrowed`) the whole-screen `WorkingFrame` shows as
/// well; the outline alone is the background case.
public final class WorkingOutline {
    private let panel: NSPanel
    private var subscription: AnyCancellable?
    private var restyle: AnyCancellable?

    public init(model: MiloModel, onStop: @escaping () -> Void) {
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered,
                        defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.ignoresMouseEvents = false
        // Only the tag and its Stop button take clicks; the rest of the panel is see-through to the app below.
        let hosting = ClickThroughHostingView(rootView: WorkingOutlineView(onStop: onStop))
        panel.contentView = hosting
        // Milo's colours, changed only when the theme is.
        restyle = model.$character.removeDuplicates().sink { [weak hosting] in
            hosting?.rootView = WorkingOutlineView(onStop: onStop, theme: Theme.for($0))
        }
        subscription = model.$workingWindow.removeDuplicates().receive(on: DispatchQueue.main)
            .sink { [weak self] frame in self?.show(frame) }
    }

    private func show(_ frame: CGRect?) {
        guard let frame else { return panel.orderOut(nil) }
        // A little room so the border sits just outside the window.
        panel.setFrame(frame.insetBy(dx: -4, dy: -4), display: true)
        if !panel.isVisible { panel.orderFrontRegardless() }
    }
}

/// Passes a click through to whatever is under it unless the click lands on a real control (the Stop button).
final class ClickThroughHostingView<Content: View>: NSHostingView<Content> {
    override func hitTest(_ point: NSPoint) -> NSView? {
        let hit = super.hitTest(point)
        return hit === self ? nil : hit
    }
}
