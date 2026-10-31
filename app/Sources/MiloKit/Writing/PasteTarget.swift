import Foundation

/// Whether text Milo wrote may be pasted where the focus is now (ADR 0033). Pure, so every case is tested.
///
/// It goes only into the field that had the focus when the talk key went down, never Milo's own window, never a
/// password field, and never a terminal, where a pasted line break runs a command. Anything else keeps the text in
/// Milo's window to copy, with the reason as a plain word the brain turns into a line.
public enum PasteTarget {
    public enum Verdict: Equatable, Sendable {
        case paste
        /// Not pasted: "here" (Milo's own window has the focus), "moved", "no_field", "secure" or "terminal".
        case keep(String)
    }

    /// Terminals: a pasted line break runs whatever is on the line.
    static let terminals: Set<String> = [
        "com.apple.Terminal", "com.googlecode.iterm2", "dev.warp.Warp-Stable", "dev.warp.Warp", "dev.warp.Warp-Preview",
        "net.kovidgoyal.kitty", "org.alacritty", "io.alacritty", "com.mitchellh.ghostty", "co.zeit.hyper",
        "com.github.wez.wezterm", "org.tabby", "com.raphaelamorim.rio", "dev.commandline.waveterm",
    ]

    /// A terminal inside another app: the input of xterm.js (VS Code, Cursor, T3 Code, Hyper) is labelled "Terminal
    /// input", VS Code's terminal pane "Terminal 1, zsh", JetBrains' tool window "Terminal".
    static let terminalWords = ["terminal", "console", "konsole", "shell"]

    /// Card numbers and security codes are as secret as passwords, even in a plain field.
    static let secretWords = ["password", "passwort", "passcode", "card number", "kartennummer", "cvv", "cvc",
                              "security code", "sicherheitscode", "prüfnummer"]

    /// `lines`: the text has line breaks. Those go only into a field that positively takes typing, so a terminal
    /// this list doesn't know (its text area is read-only to Accessibility) runs nothing.
    public static func verdict(keyDown: FocusedField?, now: FocusedField?, lines: Bool = false) -> Verdict {
        if now?.milo == true { return .keep("here") }  // typed in Milo's window, or looking at it: copy from there
        guard let keyDown else { return .keep("no_field") }
        if keyDown.milo { return .keep("here") }
        guard let now, now.pid == keyDown.pid, now.field == keyDown.field else { return .keep("moved") }
        if isSecret(now) { return .keep("secure") }
        if isTerminal(now) { return .keep("terminal") }
        guard now.editable, !lines || now.settable else { return .keep("no_field") }
        return .paste
    }

    static func isTerminal(_ field: FocusedField) -> Bool {
        terminals.contains(field.bundle) || terminalWords.contains { words(field.label).contains($0) }
    }

    static func isSecret(_ field: FocusedField) -> Bool {
        field.secure || field.role == "AXSecureTextField" || secretWords.contains { field.label.lowercased().contains($0) }
    }

    private static func words(_ text: String) -> Set<String> {
        Set(text.lowercased().split { !$0.isLetter }.map(String.init))
    }
}
