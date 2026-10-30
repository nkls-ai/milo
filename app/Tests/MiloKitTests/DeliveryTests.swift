import Testing
@testable import MiloKit

@Suite struct DeliveryTests {
    private func plan(_ action: Delivery.Action, _ traits: Delivery.Traits = .init(), _ family: Delivery.Family = .cocoa,
                      skyLight: Bool = true, borrowed: Bool = false) -> [Delivery.Step] {
        Delivery.plan(action, traits: traits, family: family, skyLight: skyLight, borrowed: borrowed)
    }

    @Test func aButtonIsPressedThroughAccessibilityFirst() {
        #expect(plan(.click(right: false, count: 1), .init(pressable: true)) == [.axPress, .processClick])
        #expect(plan(.click(right: false, count: 1), .init(pressable: true), .office) == [.axPress],
                "Office ribbon buttons press through AX; its documents ignore posted clicks")
    }

    @Test func aClickIntoTextFocusesItAndPlacesTheCaret() {
        #expect(plan(.click(right: false, count: 1), .init(textual: true)) == [.axFocus, .processClick])
    }

    @Test func chromiumNeedsTheKeyWindowTrickForPostedClicks() {
        #expect(plan(.click(right: false, count: 1), .init(), .chromium) == [.processClick])
        #expect(plan(.click(right: false, count: 1), .init(), .chromium, skyLight: false).isEmpty)
        #expect(plan(.click(right: true, count: 1), .init(), .chromium).isEmpty, "a posted right-click turns left")
        #expect(plan(.click(right: true, count: 1), .init(menu: true), .chromium) == [.axShowMenu])
    }

    @Test func typingInsertsThroughAccessibilityThenPostsKeys() {
        #expect(plan(.type) == [.axInsert, .processKeys])
        #expect(plan(.type, .init(), .chromium) == [.processKeys], "Chromium ignores AXSelectedText")
        #expect(plan(.type, .init(), .office) == [.axInsert])
    }

    @Test func chordsNeedTheWindowMadeKey() {
        #expect(plan(.key(chord: false), skyLight: false) == [.processKeys])
        #expect(plan(.key(chord: true), skyLight: false).isEmpty)
        #expect(plan(.key(chord: true)) == [.processKeys])
        #expect(plan(.key(chord: false), .init(), .office).isEmpty)
    }

    @Test func scrollingSetsTheScrollBarWhenThereIsOne() {
        #expect(plan(.scroll, .init(scrollBar: true)) == [.axScrollBar, .processScroll])
        #expect(plan(.scroll, .init(), .office).isEmpty)
    }

    @Test func theRealPointerComesLastAndOnlyWhenLent() {
        #expect(plan(.click(right: false, count: 2), .init(), .office) == [])
        #expect(plan(.click(right: false, count: 2), .init(), .office, borrowed: true) == [.real])
        #expect(plan(.type, .init(), .cocoa, borrowed: true) == [.axInsert, .processKeys, .real])
        #expect(Delivery.need(for: .click(right: false, count: 1)) == .mouse)
        #expect(Delivery.need(for: .key(chord: true)) == .keyboard)
    }

    @Test func aPostedClickIsNeverRepeatedAnotherWay() {
        #expect(!Delivery.mayFallThrough(after: .processClick, verified: false))
        #expect(!Delivery.mayFallThrough(after: .processKeys, verified: nil), "unreadable: it may have landed")
        #expect(Delivery.mayFallThrough(after: .processKeys, verified: false))
        #expect(Delivery.mayFallThrough(after: .axInsert, verified: false))
    }

    @Test func familiesComeFromTheBundle() {
        #expect(Delivery.family(bundleID: "com.microsoft.Excel", embedsChromium: false) == .office)
        #expect(Delivery.family(bundleID: "com.google.Chrome.canary", embedsChromium: false) == .chromium)
        #expect(Delivery.family(bundleID: "com.tinyspeck.slackmacgap", embedsChromium: true) == .chromium)
        #expect(Delivery.family(bundleID: "com.apple.TextEdit", embedsChromium: false) == .cocoa)
        #expect(Delivery.family(bundleID: nil, embedsChromium: false) == .cocoa)
    }
}
