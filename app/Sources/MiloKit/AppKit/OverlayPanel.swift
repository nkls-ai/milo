import AppKit
import SwiftUI

/// The transparent floating window that holds Milo. Never steals focus.
/// Dragging Milo moves it; a click on him without moving calls `onClick`.
public final class OverlayPanel: NSPanel {
    public static let size = NSSize(width: 340, height: 380)

    public var onClick: (() -> Void)? {
        get { host.onClick }
        set { host.onClick = newValue }
    }

    /// Milo's centre in the panel, from its bottom-left corner: OverlayView pins his 132 pt frame 20 pt from
    /// the right and 12 pt from the bottom, and Pip's body sits 6 pt below the middle of that frame.
    static let characterCenter = CGPoint(x: size.width - 86, y: 72)

    private let host: DraggableHostingView<OverlayView>
    private var flight: FlightDriver?

    public init(model: MiloModel) {
        host = DraggableHostingView(rootView: OverlayView(model: model))
        super.init(contentRect: NSRect(origin: .zero, size: Self.size),
                   styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        level = .floating
        hidesOnDeactivate = false
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        host.frame = NSRect(origin: .zero, size: Self.size)
        contentView = host
        flight = FlightDriver(panel: self, model: model, center: Self.characterCenter)
    }

    public override var canBecomeKey: Bool { true }

    public func placeBottomRight() {
        guard let screen = NSScreen.main else { return }
        let f = screen.visibleFrame
        setFrameOrigin(NSPoint(x: f.maxX - frame.width - 8, y: f.minY + 8))
    }

    public func toggleVisible() {
        if isVisible { orderOut(nil) } else { orderFrontRegardless() }
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

    override var mouseDownCanMoveWindow: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func mouseDown(with event: NSEvent) {
        guard let window, isOnCharacter(convert(event.locationInWindow, from: nil)) else {
            return super.mouseDown(with: event)
        }
        let startMouse = NSEvent.mouseLocation
        let startOrigin = window.frame.origin
        var dragging = false
        while let next = window.nextEvent(matching: [.leftMouseDragged, .leftMouseUp]), next.type != .leftMouseUp {
            let now = NSEvent.mouseLocation
            let dx = now.x - startMouse.x, dy = now.y - startMouse.y
            if !dragging && hypot(dx, dy) < Self.clickSlop { continue }
            dragging = true
            window.setFrameOrigin(NSPoint(x: startOrigin.x + dx, y: startOrigin.y + dy))
        }
        if !dragging { onClick?() }
    }

    private func isOnCharacter(_ p: NSPoint) -> Bool {
        let fromBottom = isFlipped ? bounds.maxY - p.y : p.y - bounds.minY
        return bounds.maxX - p.x <= Self.characterArea && fromBottom <= Self.characterArea
    }
}
