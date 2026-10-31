import AppKit
import Combine
import SwiftUI

/// The transparent floating window that holds Milo. Never steals focus.
/// Dragging Milo moves it; a click on him without moving calls `onClick`. It follows `MiloModel.presence`: out of
/// the window list while he is away, so it takes no clicks, and in again the moment he sets off back.
public final class OverlayPanel: NSPanel {
    public static let size = NSSize(width: 340, height: 380)

    /// Called on a click on Milo. The click also starts his wait before leaving over, and brings him back if he
    /// was on his way off.
    public var onClick: (() -> Void)? {
        didSet {
            host.onClick = { [weak self] in
                self?.presence.summon()
                self?.onClick?()
            }
        }
    }

    /// Milo's centre in the panel, from its bottom-left corner: OverlayView pins his 132 pt frame 20 pt from
    /// the right and 12 pt from the bottom, and Pip's body sits 6 pt below the middle of that frame.
    static let characterCenter = CGPoint(x: size.width - 86, y: 72)
    /// The Stop button's centre, the same way: on the left edge of that frame, halfway up, moved by its offset.
    static let stopCenter = CGPoint(x: size.width - 20 - 132 + StopByMilo.size / 2 + StopByMilo.offset.width,
                                    y: 12 + 66 - StopByMilo.offset.height)

    private let host: DraggableHostingView<OverlayView>
    private var flight: FlightDriver?
    private var comings: AnyCancellable?
    private let presence: Presence

    public init(model: MiloModel) {
        host = DraggableHostingView(rootView: OverlayView(model: model))
        presence = model.presence
        super.init(contentRect: NSRect(origin: .zero, size: Self.size),
                   styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .floating
        hidesOnDeactivate = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        host.frame = NSRect(origin: .zero, size: Self.size)
        // The panel keeps its size. By default the hosting view resizes its window to fit the content, and a
        // long bubble grew the panel down past the bottom of the screen, taking Milo and his Yes/No with it.
        host.sizingOptions = []
        contentView = host
        flight = FlightDriver(panel: self, model: model, center: Self.characterCenter)
        presence.reduceMotion = { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }
        host.onDrag = { [weak presence] in presence?.held = $0 }
        // The Stop button sits in Milo's square: a click on it is the button's, never a drag or a click on him.
        host.isControl = { [weak model] p in
            guard let model else { return false }
            if model.canStop && hypot(p.x - Self.stopCenter.x, p.y - Self.stopCenter.y) <= StopByMilo.size / 2 + 4 {
                return true
            }
            // The meeting capsule's Pause and Stop, whose row above him reaches into his square.
            if Self.onCards(p, model.meeting.area) { return true }
            // A done card where it reaches into his square, and the check on its corner.
            return Self.onCards(p, model.done.area)
        }
        // A panel that isn't key doesn't always hear the pointer come and go: the cards ask it.
        model.done.pointing = { [weak host, weak model] in
            guard let host, let model, !model.done.area.isEmpty else { return false }
            return host.pointer(in: model.done.area)
        }
        host.onClick = { [weak presence] in presence?.summon() }
        presence.pointing = { [weak host] in host?.pointerOnCharacter ?? false }
        // `phase` is published before it changes: the new value comes in, so he is in the window list before the
        // first frame of his way back is drawn.
        comings = model.presence.$phase.dropFirst().sink { [weak self] phase in
            guard let self else { return }
            if phase == .away {
                orderOut(nil)
            } else if !isVisible {
                orderFrontRegardless()
            }
        }
    }

    /// Whether `p` (from the panel's bottom-left corner) is on the done cards at `area` (top-left origin, as
    /// SwiftUI lays them out), with a little room for the check on a card's corner.
    static func onCards(_ p: NSPoint, _ area: CGRect) -> Bool {
        guard !area.isEmpty else { return false }
        return area.insetBy(dx: -6, dy: -6).contains(CGPoint(x: p.x, y: size.height - p.y))
    }

    public override var canBecomeKey: Bool { true }

    public func placeBottomRight() {
        guard let screen = NSScreen.main else { return }
        let f = screen.visibleFrame
        setFrameOrigin(NSPoint(x: f.maxX - frame.width - 8, y: f.minY + 8))
    }

    /// A top-left-origin point (Accessibility, CGEvent, screenshots) in AppKit's bottom-left-origin space,
    /// the space of `MiloModel.flyTarget`.
    public static func appKitPoint(_ point: ScreenPoint) -> CGPoint {
        FlightPlan.appKit(CGPoint(x: point.x, y: point.y), primaryHeight: NSScreen.screens.first?.frame.height ?? 0)
    }
}

/// Moves the window when Milo is dragged and reports a click when he isn't. The rest of the overlay
/// (the bubble) gets its mouse events as usual.
final class DraggableHostingView<Content: View>: NSHostingView<Content> {
    /// Milo sits in this corner square: pinned bottom-right by OverlayView, with its padding.
    static var characterArea: CGFloat { 172 }
    /// A press that moves less than this is a click.
    static var clickSlop: CGFloat { 3 }

    var onClick: (() -> Void)?
    /// A control inside Milo's square at this point (from the bottom-left corner) takes the click itself.
    var isControl: (NSPoint) -> Bool = { _ in false }
    /// True while Milo is dragged, false when he is let go: he doesn't leave in between.
    var onDrag: ((Bool) -> Void)?

    override var mouseDownCanMoveWindow: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        guard let window, isOnCharacter(convert(event.locationInWindow, from: nil)) else {
            return super.mouseDown(with: event)
        }
        let startMouse = NSEvent.mouseLocation
        let startOrigin = window.frame.origin
        var moved = false
        onDrag?(true)
        defer { onDrag?(false) }
        while let next = window.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]), next.type != .leftMouseUp {
            let now = NSEvent.mouseLocation
            let dx = now.x - startMouse.x, dy = now.y - startMouse.y
            if !moved && hypot(dx, dy) < Self.clickSlop { continue }
            moved = true
            window.setFrameOrigin(NSPoint(x: startOrigin.x + dx, y: startOrigin.y + dy))
        }
        if !moved { onClick?() }
    }

    /// The pointer is on Milo now.
    var pointerOnCharacter: Bool {
        guard let window, window.isVisible else { return false }
        return isOnCharacter(convert(window.mouseLocationOutsideOfEventStream, from: nil))
    }

    /// The pointer is inside `area` now, in SwiftUI's top-left-origin points of this view.
    func pointer(in area: CGRect) -> Bool {
        guard let window, window.isVisible else { return false }
        let p = convert(window.mouseLocationOutsideOfEventStream, from: nil)
        let fromTop = isFlipped ? p.y - bounds.minY : bounds.maxY - p.y
        return area.contains(CGPoint(x: p.x - bounds.minX, y: fromTop))
    }

    /// A press here drags Milo or clicks him: his square, less any control in it.
    func isOnCharacter(_ p: NSPoint) -> Bool {
        let fromBottom = isFlipped ? bounds.maxY - p.y : p.y - bounds.minY
        if isControl(NSPoint(x: p.x - bounds.minX, y: fromBottom)) { return false }
        return bounds.maxX - p.x <= Self.characterArea && fromBottom <= Self.characterArea
    }
}
