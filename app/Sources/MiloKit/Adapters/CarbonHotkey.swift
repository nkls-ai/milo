import Carbon.HIToolbox

/// A global shortcut through Carbon's RegisterEventHotKey: it works in every app, needs no permission,
/// and the key press doesn't reach the app in front.
public final class CarbonHotkey: HotkeySource {
    public var onPress: (() -> Void)?
    private var hotKey: EventHotKeyRef?
    private var handler: EventHandlerRef?
    private static let signature: OSType = 0x4D69_6C6F  // "Milo"

    public init() {}

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
        let id = EventHotKeyID(signature: Self.signature, id: 1)
        return RegisterEventHotKey(UInt32(combo.keyCode), modifiers, id, GetApplicationEventTarget(), 0, &hotKey) == noErr
    }

    private func installHandler() {
        guard handler == nil else { return }
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let me = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(GetApplicationEventTarget(), { _, _, data in
            guard let data else { return OSStatus(eventNotHandledErr) }
            let hotkey = Unmanaged<CarbonHotkey>.fromOpaque(data).takeUnretainedValue()
            DispatchQueue.main.async { hotkey.onPress?() }
            return noErr
        }, 1, &spec, me, &handler)
    }
}
