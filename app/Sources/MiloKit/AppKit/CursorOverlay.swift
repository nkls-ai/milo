import AppKit
import Combine
import QuartzCore
import SwiftUI

/// Milo's cursor as a click-through overlay panel, above everything and on every space. It never touches the
/// system cursor. `glide` animates the panel along `CursorGlide` 60 times a second while moving and not at all
/// at rest. Implements `CursorDisplay`, called on the main queue.
public final class CursorOverlay: CursorDisplay {
    private let panel: NSPanel
    private let hosted: NSHostingView<MiloCursorView>
    /// The pointer tip inside the panel, from its bottom-left corner (the view draws the tip at its top-left).
    private static let tip = CGPoint(x: 2, y: 94)
    private var gesture: MiloCursorView.Gesture = .none { didSet { render() } }
    private var presence = 0.0 { didSet { render() } }
    private var clickTick = 0 { didSet { render() } }
    private var timer: Timer?
    private var restTimer: Timer?

    public init() {
        hosted = NSHostingView(rootView: MiloCursorView(gesture: .none, presence: 0, clickTick: 0))
        panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 72, height: 96),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.ignoresMouseEvents = true
        panel.level = .screenSaver
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.contentView = hosted
    }

    public func glide(to point: CGPoint, arrived: @escaping () -> Void) {
        restTimer?.invalidate()
        restTimer = nil
        // Everything here is in AppKit coordinates (origin bottom-left), the space CursorGlide works in.
        let end = OverlayPanel.appKitPoint(ScreenPoint(x: point.x, y: point.y))
        if presence == 0 { place(tip: CursorGlide.entry(for: end)) }
        presence = 1
        if !panel.isVisible { panel.orderFrontRegardless() }
        let start = CGPoint(x: origin.x + Self.tip.x, y: origin.y + Self.tip.y)
        let distance = hypot(end.x - start.x, end.y - start.y)
        timer?.invalidate()
        if distance < 1 || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            place(tip: end)
            return arrived()
        }
        let duration = CursorGlide.duration(distance)
        let began = CACurrentMediaTime()
        let timer = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] timer in
            guard let self else { return timer.invalidate() }
            let t = min(1, (CACurrentMediaTime() - began) / duration)
            place(tip: CursorGlide.point(from: start, to: end, at: t))
            if t >= 1 { timer.invalidate(); self.timer = nil; arrived() }
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    public func click(at point: CGPoint) {
        place(tip: OverlayPanel.appKitPoint(ScreenPoint(x: point.x, y: point.y)))
        gesture = .click
        clickTick += 1
        // The ripple plays once; back to a plain pointer after it.
        after(0.5) { [weak self] in if self?.gesture == .click { self?.gesture = .none } }
    }

    public func typing(at point: CGPoint) {
        if point != .zero { place(tip: OverlayPanel.appKitPoint(ScreenPoint(x: point.x, y: point.y))) }
        gesture = .typing
    }

    public func rest() {
        timer?.invalidate()
        timer = nil
        gesture = .none
        presence = 0
        restTimer?.invalidate()
        restTimer = after(0.3) { [weak self] in self?.panel.orderOut(nil) }
    }

    private var origin: CGPoint { panel.frame.origin }

    /// Places the pointer tip at a point in AppKit coordinates (origin bottom-left).
    private func place(tip appKitTip: CGPoint) {
        panel.setFrameOrigin(CGPoint(x: appKitTip.x - Self.tip.x, y: appKitTip.y - Self.tip.y))
    }

    private func render() {
        hosted.rootView = MiloCursorView(gesture: gesture, presence: presence, clickTick: clickTick)
    }

    @discardableResult
    private func after(_ seconds: TimeInterval, _ work: @escaping () -> Void) -> Timer {
        let timer = Timer(timeInterval: seconds, repeats: false) { _ in work() }
        RunLoop.main.add(timer, forMode: .common)
        return timer
    }
}
