import Testing
@testable import MiloKit

@Suite struct DeliveryTests {
    private func plan(_ action: Delivery.Action, _ traits: Delivery.Traits = .init(), _ family: Delivery.Family = .cocoa,
                      borrowed: Bool = false) -> [Delivery.Step] {
        Delivery.plan(action, traits: traits, family: family, borrowed: borrowed)
    }

    @Test func aButtonIsPressedThroughAccessibility() {
        #expect(plan(.click(right: false, count: 1), .init(pressable: true)) == [.axPress])
        #expect(plan(.click(right: false, count: 1), .init(pressable: true), .office) == [.axPress],
                "Office ribbon buttons press through Accessibility")
    }

    @Test func aClickIntoTextFocusesItAndPlacesTheCaret() {
        #expect(plan(.click(right: false, count: 1), .init(textual: true)) == [.axFocus])
    }

    @Test func aRightClickOpensTheElementsMenu() {
        #expect(plan(.click(right: true, count: 1), .init(menu: true)) == [.axShowMenu])
        #expect(plan(.click(right: true, count: 1)).isEmpty)
    }

    @Test func typingInsertsThroughAccessibilityWhereTheAppAllowsIt() {
        #expect(plan(.type, .init(insertable: true)) == [.axInsert])
        #expect(plan(.type, .init(insertable: true), .chromium).isEmpty, "Chromium ignores AXSelectedText")
        #expect(plan(.type).isEmpty)
    }

    @Test func scrollingSetsTheScrollBarWhenThereIsOne() {
        #expect(plan(.scroll, .init(scrollBar: true)) == [.axScrollBar])
        #expect(plan(.scroll).isEmpty)
    }

    @Test func doubleClicksAndKeysNeedTheRealOnes() {
        #expect(plan(.click(right: false, count: 2), .init(pressable: true)).isEmpty)
        #expect(plan(.key).isEmpty)
    }

    @Test func theRealPointerComesLastAndOnlyWhenLent() {
        #expect(plan(.click(right: false, count: 2), borrowed: true) == [.real])
        #expect(plan(.type, .init(insertable: true), borrowed: true) == [.axInsert, .real])
        #expect(Delivery.need(for: .click(right: false, count: 1)) == .mouse)
        #expect(Delivery.need(for: .key) == .keyboard)
    }

    @Test func familiesComeFromTheBundle() {
        #expect(Delivery.family(bundleID: "com.microsoft.Excel", embedsChromium: false) == .office)
        #expect(Delivery.family(bundleID: "com.google.Chrome.canary", embedsChromium: false) == .chromium)
        #expect(Delivery.family(bundleID: "com.tinyspeck.slackmacgap", embedsChromium: true) == .chromium)
        #expect(Delivery.family(bundleID: "com.apple.TextEdit", embedsChromium: false) == .cocoa)
        #expect(Delivery.family(bundleID: nil, embedsChromium: false) == .cocoa)
    }
}
