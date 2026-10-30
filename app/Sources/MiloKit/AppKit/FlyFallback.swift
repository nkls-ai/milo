import AppKit
import Combine

/// A plain stand-in for flying: moves the overlay so Milo sits just below and right of `flyTarget`, and
/// back to where he was when it clears. The character's own flying and pointing can replace this by
/// observing `MiloModel.flyTarget` instead; main.swift is the only place that creates it.
public final class FlyFallback {
    private let panel: OverlayPanel
    private var home: NSPoint?
    private var subscription: AnyCancellable?

    public init(model: MiloModel, panel: OverlayPanel) {
        self.panel = panel
        subscription = model.$flyTarget.removeDuplicates().receive(on: DispatchQueue.main).sink { [weak self] in
            self?.fly(to: $0)
        }
    }

    /// A top-left-origin point (Accessibility, CGEvent) in AppKit's bottom-left-origin space.
    public static func appKitPoint(_ point: ScreenPoint) -> CGPoint {
        let height = NSScreen.screens.first?.frame.height ?? 0
        return CGPoint(x: point.x, y: height - point.y)
    }

    private func fly(to target: CGPoint?) {
        guard let target else {
            if let home { move(to: home) }
            home = nil
            return
        }
        if home == nil { home = panel.frame.origin }
        let area = DraggableHostingView<OverlayView>.characterArea
        // The character's centre goes 70 points right of and below the target, so he doesn't cover it.
        var origin = NSPoint(x: target.x + 70 + area / 2 - panel.frame.width, y: target.y - 70 - area / 2)
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(target) }) ?? NSScreen.main {
            let f = screen.visibleFrame
            origin.x = min(max(origin.x, f.minX - panel.frame.width + area), f.maxX - panel.frame.width)
            origin.y = min(max(origin.y, f.minY), f.maxY - panel.frame.height)
        }
        move(to: origin)
    }

    private func move(to origin: NSPoint) {
        NSAnimationContext.runAnimationGroup { context in
            context.duration = 0.35
            context.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
            panel.animator().setFrameOrigin(origin)
        }
    }
}
