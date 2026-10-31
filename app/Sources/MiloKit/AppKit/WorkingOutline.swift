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
    private var restyle: AnyCancellable?
    private var timer: Timer?

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
        panel.contentView = hosting
        // Milo's colours, changed only when the theme is.
        restyle = model.$character.removeDuplicates().sink { [weak hosting] in
            hosting?.rootView = WorkingOutlineView(theme: Theme.for($0))
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
        // A little room so the border sits just outside the window.
        panel.setFrame(frame.insetBy(dx: -4, dy: -4), display: true)
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
