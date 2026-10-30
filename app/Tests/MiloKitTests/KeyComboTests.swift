import Testing
@testable import MiloKit

@Suite struct KeyComboTests {
    @Test func parsesModifiersAndOneKey() {
        #expect(KeyCombo("ctrl+option+m") == KeyCombo(modifiers: [.control, .option], keyCode: 46))
        #expect(KeyCombo("Cmd + Shift + S") == KeyCombo(modifiers: [.command, .shift], keyCode: 1))
        #expect(KeyCombo("return") == KeyCombo(modifiers: [], keyCode: 36))
        #expect(KeyCombo("f5") == KeyCombo(modifiers: [], keyCode: 96))
        #expect(KeyCombo("⌘+⌥+esc") == KeyCombo(modifiers: [.command, .option], keyCode: 53))
    }

    @Test func rejectsWhatItCantPress() {
        #expect(KeyCombo("") == nil)
        #expect(KeyCombo("ctrl+option") == nil)
        #expect(KeyCombo("cmd+a+b") == nil)
        #expect(KeyCombo("hyper+m") == nil)
        #expect(KeyCombo("ctrl++m") == nil)
    }

    @Test func showsLikeAMacMenu() {
        #expect(KeyCombo("ctrl+option+m")?.displayName == "⌃⌥M")
        #expect(KeyCombo("cmd+shift+return")?.displayName == "⇧⌘↩")
    }
}
