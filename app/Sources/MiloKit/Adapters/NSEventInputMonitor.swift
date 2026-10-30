import AppKit

/// Mouse and keyboard input in every app, for stopping the worker when the user takes over.
/// Global monitors see other apps (keys need Accessibility); a local one sees esc in Milo's own windows.
public final class NSEventInputMonitor: UserInputSource {
    public var onInput: ((UserInput) -> Void)?
    private var monitors: [Any] = []

    public init() {}

    deinit {
        monitors.forEach(NSEvent.removeMonitor)
    }

    public func start() {
        guard monitors.isEmpty else { return }
        let mask: NSEvent.EventTypeMask = [.mouseMoved, .leftMouseDown, .rightMouseDown, .otherMouseDown,
                                           .leftMouseDragged, .rightMouseDragged, .scrollWheel, .keyDown]
        if let global = NSEvent.addGlobalMonitorForEvents(matching: mask, handler: { [weak self] in self?.emit($0) }) {
            monitors.append(global)
        }
        if let local = NSEvent.addLocalMonitorForEvents(matching: [.keyDown], handler: { [weak self] in
            self?.emit($0)
            return $0
        }) {
            monitors.append(local)
        }
    }

    public func stop() {
        monitors.forEach(NSEvent.removeMonitor)
        monitors.removeAll()
    }

    private func emit(_ event: NSEvent) {
        let synthetic = event.cgEvent?.getIntegerValueField(.eventSourceUserData) == PasteboardInserter.eventMarker
        let kind: UserInput.Kind
        switch event.type {
        case .mouseMoved, .leftMouseDragged, .rightMouseDragged:
            let p = NSEvent.mouseLocation
            kind = .mouseMoved(x: p.x, y: p.y)
        case .leftMouseDown, .rightMouseDown, .otherMouseDown: kind = .mouseDown
        case .scrollWheel: kind = .scroll
        case .keyDown: kind = event.keyCode == KeyEvent.escapeKeyCode ? .escape : .key
        default: return
        }
        onInput?(UserInput(kind, at: event.timestamp, synthetic: synthetic))
    }
}
