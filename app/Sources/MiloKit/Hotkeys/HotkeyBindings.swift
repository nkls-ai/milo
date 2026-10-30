/// Which key to hold for each listen mode.
public struct HotkeyBindings: Equatable, Sendable {
    public var dictate: ModifierKey
    public var talk: ModifierKey

    public init(dictate: ModifierKey, talk: ModifierKey) {
        self.dictate = dictate
        self.talk = talk
    }

    public static let `default` = HotkeyBindings(dictate: .fn, talk: .rightOption)

    public func mode(forKeyCode code: UInt16) -> ListenMode? {
        if code == dictate.keyCode { return .dictate }
        if code == talk.keyCode { return .talk }
        return nil
    }

    /// The menu line, e.g. "Hold fn to dictate · hold right ⌥ to talk · double-tap for hands-free".
    public var hint: String {
        "Hold \(dictate.displayName) to dictate · hold \(talk.displayName) to talk · double-tap for hands-free"
    }

    /// Bindings from `ui_config` key names. An unknown name keeps the current key for that mode;
    /// if both modes would end up on the same key, nothing changes.
    public func applying(dictateKey: String, talkKey: String) -> HotkeyBindings {
        let next = HotkeyBindings(dictate: ModifierKey(rawValue: dictateKey) ?? dictate,
                                  talk: ModifierKey(rawValue: talkKey) ?? talk)
        return next.dictate == next.talk ? self : next
    }
}
