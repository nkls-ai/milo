import AppKit

/// Types text into the focused app by pasting with Cmd-V, then restores the user's clipboard.
///
/// Live dictation pastes several times in a row. The clipboard saved before the first paste is the one
/// restored after the last, so a quick second paste doesn't save (and later restore) the first one's text.
public final class PasteboardInserter: TextInserter {
    /// Set as the source user data of the Cmd-V events Milo posts, so the key monitor can ignore them.
    public static let eventMarker: Int64 = 0x4D69_6C6F  // "Milo"

    private let pasteboard: NSPasteboard
    private let scheduler: Scheduler
    private let restoreDelay: TimeInterval
    private var pendingRestore: (saved: [NSPasteboardItem], changeCount: Int, task: ScheduledTask)?

    public init(pasteboard: NSPasteboard = .general, scheduler: Scheduler, restoreDelay: TimeInterval = 0.6) {
        self.pasteboard = pasteboard
        self.scheduler = scheduler
        self.restoreDelay = restoreDelay
    }

    public func insert(_ text: String) {
        let board = pasteboard
        let saved: [NSPasteboardItem]
        if let pending = pendingRestore, pending.changeCount == board.changeCount {
            pending.task.cancel()
            saved = pending.saved
        } else {
            pendingRestore?.task.cancel()
            saved = board.pasteboardItems?.map { item -> NSPasteboardItem in
                let copy = NSPasteboardItem()
                for type in item.types {
                    if let data = item.data(forType: type) { copy.setData(data, forType: type) }
                }
                return copy
            } ?? []
        }

        board.clearContents()
        board.setString(text, forType: .string)
        let changeCount = board.changeCount
        Self.sendCommandV()

        let task = scheduler.after(restoreDelay) { [weak self] in
            self?.pendingRestore = nil
            // Leave the clipboard alone if the user copied something in the meantime.
            guard board.changeCount == changeCount else { return }
            board.clearContents()
            if !saved.isEmpty { board.writeObjects(saved) }
        }
        pendingRestore = (saved, changeCount, task)
    }

    private static func sendCommandV() {
        let source = CGEventSource(stateID: .combinedSessionState)
        let vKey: CGKeyCode = 9
        let down = CGEvent(keyboardEventSource: source, virtualKey: vKey, keyDown: true)
        let up = CGEvent(keyboardEventSource: source, virtualKey: vKey, keyDown: false)
        for event in [down, up] {
            event?.flags = .maskCommand
            event?.setIntegerValueField(.eventSourceUserData, value: eventMarker)
            event?.post(tap: .cghidEventTap)
        }
    }
}
