import AppKit
import Combine
import SwiftUI

/// A borderless panel that outlines the window Milo works in. It follows `MiloModel.workingWindow` (AppKit
/// coordinates) and sits just above that window (`workingWindowNumber`), so windows in front of it cover the
/// outline too, and it goes with the window when that is minimized or hidden. Every click goes through it: it
/// sits over the app and under Milo, whose Stop button and questions must always take a click.
/// When the real mouse and keyboard are borrowed (`handsBorrowed`) the whole-screen `WorkingFrame` shows as
/// well; the outline alone is the background case.
public final class WorkingOutline {
    /// How often it checks it is still just above the window, which comes up over it when the user clicks in it.
    static let restack: TimeInterval = 0.25

    private let panel: NSPanel
    private let model: MiloModel
    private var subscription: AnyCancellable?
    private var captioning: AnyCancellable?
    private var timer: Timer?
    private var hosting: NSHostingView<WorkingOutlineView>?
    private let theme = Theme.milo
    private var caption: String?
    /// The panel reaches below the window for the caption; false where the window goes down to the screen's edge.
    private var below = true

    public init(model: MiloModel) {
        self.model = model
        panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered,
                        defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        let hosting = NSHostingView(rootView: WorkingOutlineView())
        hosting.sizingOptions = []
        self.hosting = hosting
        panel.contentView = hosting
        // The step he is on, changed only when it is.
        captioning = model.$workingStep.removeDuplicates()
            .receive(on: DispatchQueue.main)
            .sink { [weak self] step in
                guard let self else { return }
                caption = step
                redraw()
            }
        subscription = model.$workingWindow.combineLatest(model.$workingWindowNumber)
            .removeDuplicates { $0 == $1 }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] frame, number in self?.show(frame, above: number) }
    }

    private func show(_ frame: CGRect?, above number: Int?) {
        guard let frame else {
            timer?.invalidate()
            timer = nil
            return panel.orderOut(nil)
        }
        // A little room so the border sits just outside the window, and below it for the caption when the screen
        // has it.
        var outline = frame.insetBy(dx: -4, dy: -4)
        let room = WorkingOutlineView.captionRoom
        let bottom = NSScreen.screens.first { $0.frame.intersects(frame) }?.frame.minY ?? -.infinity
        let fits = outline.minY - room >= bottom
        if fits { outline = CGRect(x: outline.minX, y: outline.minY - room, width: outline.width,
                                   height: outline.height + room) }
        if fits != below {
            below = fits
            redraw()
        }
        panel.setFrame(outline, display: true)
        guard let number else {
            // Window unknown to the window server: above the other apps, still under Milo.
            panel.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue - 1)
            if !panel.isVisible { panel.orderFrontRegardless() }
            return
        }
        panel.level = .normal
        stack(above: number)
        if timer == nil {
            let timer = Timer(timeInterval: Self.restack, repeats: true) { [weak self] _ in
                guard let self, let number = model.workingWindowNumber else { return }
                stack(above: number)
            }
            RunLoop.main.add(timer, forMode: .common)
            self.timer = timer
        }
    }

    private func redraw() {
        hosting?.rootView = WorkingOutlineView(theme: theme, caption: caption, below: below)
    }

    /// Puts the outline just above window `number`, unless it is already there.
    private func stack(above number: Int) {
        if panel.isVisible && Self.directlyAbove(panel.windowNumber, number) { return }
        panel.order(.above, relativeTo: number)
    }

    /// Whether `ours` is the nearest normal window above `target`: nothing of the same layer sits between them.
    static func directlyAbove(_ ours: Int, _ target: Int) -> Bool {
        guard let above = CGWindowListCopyWindowInfo([.optionOnScreenAboveWindow], CGWindowID(target))
                as? [[String: Any]] else { return false }
        let normal = above.filter { $0[kCGWindowLayer as String] as? Int == 0 }
        return normal.last?[kCGWindowNumber as String] as? Int == ours
    }
}
