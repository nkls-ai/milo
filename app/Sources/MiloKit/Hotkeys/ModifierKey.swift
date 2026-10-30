/// A modifier key that can be held for push-to-talk. Raw values are the `ui_config` key names.
public enum ModifierKey: String, CaseIterable, Sendable {
    case fn
    case rightOption = "right_option"
    case rightCommand = "right_command"
    case rightControl = "right_control"

    /// macOS virtual key code.
    public var keyCode: UInt16 {
        switch self {
        case .fn: 63
        case .rightOption: 61
        case .rightCommand: 54
        case .rightControl: 62
        }
    }

    /// The modifier flag bit that is set while the key is held.
    public var flagMask: UInt {
        switch self {
        case .fn: ModifierFlag.function
        case .rightOption: ModifierFlag.option
        case .rightCommand: ModifierFlag.command
        case .rightControl: ModifierFlag.control
        }
    }

    /// How the menu names the key.
    public var displayName: String {
        switch self {
        case .fn: "fn"
        case .rightOption: "right ⌥"
        case .rightCommand: "right ⌘"
        case .rightControl: "right ⌃"
        }
    }
}

/// Device-independent modifier bits, equal to `NSEvent.ModifierFlags` raw values, so the logic needs no AppKit.
public enum ModifierFlag {
    public static let capsLock: UInt = 1 << 16
    public static let shift: UInt = 1 << 17
    public static let control: UInt = 1 << 18
    public static let option: UInt = 1 << 19
    public static let command: UInt = 1 << 20
    public static let function: UInt = 1 << 23

    /// The flag a modifier key sets, by virtual key code (left and right share one), or nil for other keys.
    public static func mask(forKeyCode code: UInt16) -> UInt? {
        switch code {
        case 54, 55: command
        case 56, 60: shift
        case 57: capsLock
        case 58, 61: option
        case 59, 62: control
        case 63: function
        default: nil
        }
    }

    /// The device-dependent bit (NX_DEVICE*KEYMASK, low 16 bits of the flags) that only this physical key
    /// sets, or nil for fn and caps lock, which have none.
    public static func deviceMask(forKeyCode code: UInt16) -> UInt? {
        switch code {
        case 59: 0x0001  // left control
        case 56: 0x0002  // left shift
        case 60: 0x0004  // right shift
        case 55: 0x0008  // left command
        case 54: 0x0010  // right command
        case 58: 0x0020  // left option
        case 61: 0x0040  // right option
        case 62: 0x2000  // right control
        default: nil
        }
    }

    /// Whether the modifier key with this code is held, given the flags of its flags-changed event.
    ///
    /// Left and right keys share one flag, so releasing right ⌥ while left ⌥ is held leaves the option
    /// flag set. The device-dependent bits tell them apart; events without them (synthesized ones)
    /// fall back to the shared flag.
    public static func isDown(keyCode code: UInt16, flags: UInt) -> Bool {
        guard let shared = mask(forKeyCode: code), flags & shared != 0 else { return false }
        guard let own = deviceMask(forKeyCode: code) else { return true }
        let siblings = (54...62).filter { mask(forKeyCode: $0) == shared }.compactMap { deviceMask(forKeyCode: $0) }
        let anyDeviceBit = siblings.reduce(0, |)
        return flags & anyDeviceBit == 0 || flags & own != 0
    }
}
