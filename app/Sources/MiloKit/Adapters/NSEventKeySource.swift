import AppKit

/// Key events from global and local NSEvent monitors. Global monitors need the Accessibility permission.
public final class NSEventKeySource: KeyEventSource {
    public var onEvent: ((KeyEvent) -> Void)?
    private var monitors: [Any] = []

    public init() {}

    deinit {
        monitors.forEach(NSEvent.removeMonitor)
    }

    public func start() {
        guard monitors.isEmpty else { return }
        let mask: NSEvent.EventTypeMask = [.flagsChanged, .keyDown]
        if let global = NSEvent.addGlobalMonitorForEvents(matching: mask, handler: { [weak self] in self?.emit($0) }) {
            monitors.append(global)
        }
        if let local = NSEvent.addLocalMonitorForEvents(matching: mask, handler: { [weak self] in
            self?.emit($0)
            return $0
        }) {
            monitors.append(local)
        }
    }

    private func emit(_ event: NSEvent) {
        // Milo's own Cmd-V must not count as the user typing, or pasting mid-hold would cancel the hold.
        if event.cgEvent?.getIntegerValueField(.eventSourceUserData) == PasteboardInserter.eventMarker { return }
        switch event.type {
        case .keyDown:
            onEvent?(.keyDown(keyCode: event.keyCode, at: event.timestamp))
        case .flagsChanged:
            onEvent?(.flagsChanged(keyCode: event.keyCode, flags: event.modifierFlags.rawValue, at: event.timestamp))
        default:
            break
        }
    }
}
