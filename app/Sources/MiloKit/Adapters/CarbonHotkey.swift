import Carbon.HIToolbox

/// A global shortcut through Carbon's RegisterEventHotKey: it works in every app, needs no permission,
/// and the key press doesn't reach the app in front.
public final class CarbonHotkey: HotkeySource {
    public var onPress: (() -> Void)?
    private var hotKey: EventHotKeyRef?
    private var handler: EventHandlerRef?
    private static let signature: OSType = 0x4D69_6C6F  // "Milo"
    private static var lastID: UInt32 = 0
    /// Each shortcut has its own id. Every handler sees every hotkey press of the app, so it takes only its own.
    private let id: UInt32

    public init() {
        Self.lastID += 1
        id = Self.lastID
    }

    deinit {
        register(nil)
        if let handler { RemoveEventHandler(handler) }
    }

    @discardableResult
    public func register(_ combo: KeyCombo?) -> Bool {
        if let hotKey { UnregisterEventHotKey(hotKey) }
        hotKey = nil
        guard let combo else { return true }
        installHandler()
        var modifiers: UInt32 = 0
        if combo.modifiers.contains(.command) { modifiers |= UInt32(cmdKey) }
        if combo.modifiers.contains(.shift) { modifiers |= UInt32(shiftKey) }
        if combo.modifiers.contains(.option) { modifiers |= UInt32(optionKey) }
        if combo.modifiers.contains(.control) { modifiers |= UInt32(controlKey) }
        let hotKeyID = EventHotKeyID(signature: Self.signature, id: id)
        return RegisterEventHotKey(UInt32(combo.keyCode), modifiers, hotKeyID, GetApplicationEventTarget(), 0,
                                   &hotKey) == noErr
    }

    private func installHandler() {
        guard handler == nil else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let me = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(GetApplicationEventTarget(), { _, event, data in
            guard let event, let data else { return OSStatus(eventNotHandledErr) }
            var pressed = EventHotKeyID()
            let read = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                                         nil, MemoryLayout<EventHotKeyID>.size, nil, &pressed)
            let hotkey = Unmanaged<CarbonHotkey>.fromOpaque(data).takeUnretainedValue()
            // Another Milo shortcut: let its own handler have it.
            guard read == noErr, pressed.signature == CarbonHotkey.signature, pressed.id == hotkey.id else {
                return OSStatus(eventNotHandledErr)
            }
            DispatchQueue.main.async { hotkey.onPress?() }
            return noErr
        }, 1, &spec, me, &handler)
    }
}
