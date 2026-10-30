/// A shortcut such as "ctrl+option+m" or "cmd+shift+s": modifiers and one key.
public struct KeyCombo: Equatable, Hashable, Sendable {
    public struct Modifiers: OptionSet, Hashable, Sendable {
        public let rawValue: Int
        public init(rawValue: Int) { self.rawValue = rawValue }

        public static let control = Modifiers(rawValue: 1)
        public static let option = Modifiers(rawValue: 2)
        public static let shift = Modifiers(rawValue: 4)
        public static let command = Modifiers(rawValue: 8)
    }

    public var modifiers: Modifiers
    /// Virtual key code (kVK_*).
    public var keyCode: UInt16

    public init(modifiers: Modifiers, keyCode: UInt16) {
        self.modifiers = modifiers
        self.keyCode = keyCode
    }

    /// nil if a part isn't a known modifier or key, or there is not exactly one key.
    public init?(_ text: String) {
        var modifiers: Modifiers = []
        var key: UInt16?
        let parts = text.lowercased().replacingOccurrences(of: " ", with: "").split(separator: "+", omittingEmptySubsequences: false)
        for part in parts.map(String.init) {
            if let modifier = Self.modifierNames[part] {
                modifiers.insert(modifier)
            } else if let code = Self.keyCodes[Self.aliases[part] ?? part], key == nil {
                key = code
            } else {
                return nil
            }
        }
        guard let key else { return nil }
        self.init(modifiers: modifiers, keyCode: key)
    }

    /// "⌃⌥M".
    public var displayName: String {
        var text = ""
        if modifiers.contains(.control) { text += "⌃" }
        if modifiers.contains(.option) { text += "⌥" }
        if modifiers.contains(.shift) { text += "⇧" }
        if modifiers.contains(.command) { text += "⌘" }
        let name = Self.keyCodes.first { $0.value == keyCode }.map(\.key) ?? "?"
        return text + (Self.symbols[name] ?? (name.count == 1 ? name.uppercased() : name.capitalized))
    }

    static let modifierNames: [String: Modifiers] = [
        "ctrl": .control, "control": .control, "⌃": .control,
        "option": .option, "opt": .option, "alt": .option, "⌥": .option,
        "shift": .shift, "⇧": .shift,
        "cmd": .command, "command": .command, "⌘": .command,
    ]

    static let symbols = ["return": "↩", "tab": "⇥", "space": "Space", "delete": "⌫", "escape": "⎋",
                          "left": "←", "right": "→", "up": "↑", "down": "↓"]

    static let aliases = ["enter": "return", "backspace": "delete", "esc": "escape"]

    /// US layout virtual key codes, the same on every Mac keyboard for these names.
    static let keyCodes: [String: UInt16] = {
        var codes: [String: UInt16] = [
            "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12,
            "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23,
            "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34,
            "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46,
            ".": 47, "`": 50,
            "return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53, "forwarddelete": 117, "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
            "left": 123, "right": 124, "down": 125, "up": 126, "keypadenter": 76,
        ]
        let fKeys: [UInt16] = [122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111, 105, 107, 113, 106, 64, 79, 80]
        for (i, code) in fKeys.enumerated() { codes["f\(i + 1)"] = code }
        return codes
    }()
}
