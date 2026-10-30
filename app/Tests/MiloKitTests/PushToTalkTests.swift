import Foundation
import Testing
@testable import MiloKit

private func down(_ key: ModifierKey, at time: TimeInterval) -> KeyEvent {
    KeyEvent(.modifierChanged(keyCode: key.keyCode, isDown: true), at: time)
}

private func up(_ key: ModifierKey, at time: TimeInterval) -> KeyEvent {
    KeyEvent(.modifierChanged(keyCode: key.keyCode, isDown: false), at: time)
}

/// Left ⌥, which shares its flag with right ⌥.
private let leftOptionCode: UInt16 = 58
/// NX_DEVICELALTKEYMASK / NX_DEVICERALTKEYMASK: the per-key bits in NSEvent.modifierFlags.
private let leftOptionBit: UInt = 0x20
private let rightOptionBit: UInt = 0x40

private func esc(at time: TimeInterval) -> KeyEvent {
    .keyDown(keyCode: KeyEvent.escapeKeyCode, at: time)
}

/// Feeds a double tap of `key` starting at `time`: down, up 80 ms later, down again at +200 ms, up at +280 ms.
private func doubleTap(_ key: ModifierKey, at time: TimeInterval, into ptt: inout PushToTalk) -> [PushToTalk.Output] {
    [down(key, at: time), up(key, at: time + 0.08), down(key, at: time + 0.2), up(key, at: time + 0.28)]
        .flatMap { ptt.handle($0) }
}

@Suite struct PushToTalkTests {
    // MARK: Holding

    @Test func holdStartsTentativelyConfirmsAtMinHoldAndStopsOnRelease() {
        var ptt = PushToTalk(minHold: 0.25)
        #expect(ptt.handle(down(.rightOption, at: 10)) == [.start(.talk)])
        #expect(ptt.active == .talk)
        #expect(ptt.deadline == 10.25)
        #expect(ptt.expire(at: 10.2) == [], "too early")
        #expect(ptt.expire(at: 10.25) == [.confirm(.talk)])
        #expect(ptt.deadline == nil)
        #expect(ptt.handle(up(.rightOption, at: 11)) == [.stop(.talk)])
        #expect(ptt.active == nil)
    }

    @Test func releaseAfterMinHoldStopsEvenIfTheTimerWasLate() {
        var ptt = PushToTalk(minHold: 0.25)
        _ = ptt.handle(down(.fn, at: 20))
        #expect(ptt.handle(up(.fn, at: 20.25)) == [.stop(.dictate)])
        #expect(ptt.expire(at: 20.25) == [])
    }

    @Test func keyDownDuringHoldCancels() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        #expect(ptt.handle(KeyEvent(.keyDown, at: 0.5)) == [.cancel(.dictate)])
        // The release that follows the shortcut does nothing.
        #expect(ptt.handle(up(.fn, at: 1)) == [])
        #expect(ptt.active == nil)
    }

    @Test func escDuringHoldCancels() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        _ = ptt.expire(at: 0.25)
        #expect(ptt.handle(esc(at: 0.5)) == [.cancel(.dictate)])
    }

    @Test func keyDownWithoutHoldDoesNothing() {
        var ptt = PushToTalk()
        #expect(ptt.handle(KeyEvent(.keyDown, at: 0)) == [])
        #expect(ptt.handle(esc(at: 0)) == [])
    }

    @Test func otherModifierDuringHoldCancels() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.rightOption, at: 0))
        let shift = KeyEvent.flagsChanged(keyCode: 56, flags: ModifierFlag.option | ModifierFlag.shift, at: 0.5)
        #expect(ptt.handle(shift) == [.cancel(.talk)])
        #expect(ptt.handle(up(.rightOption, at: 1)) == [])
    }

    @Test func otherModifierWithoutHoldDoesNothing() {
        var ptt = PushToTalk()
        #expect(ptt.handle(.flagsChanged(keyCode: 55, flags: ModifierFlag.command, at: 0)) == [])
    }

    @Test func otherBindingDuringHoldIsIgnored() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        #expect(ptt.handle(down(.rightOption, at: 0.5)) == [])
        #expect(ptt.handle(up(.rightOption, at: 0.7)) == [])
        #expect(ptt.active == .dictate)
        #expect(ptt.handle(up(.fn, at: 1)) == [.stop(.dictate)])
    }

    @Test func releaseOfUnheldBindingDoesNothing() {
        var ptt = PushToTalk()
        #expect(ptt.handle(up(.fn, at: 1)) == [])
    }

    // MARK: Taps

    @Test func singleTapShowsNothingAndCancelsWhenTheWindowCloses() {
        var ptt = PushToTalk(minHold: 0.25, doubleTap: 0.35)
        #expect(ptt.handle(down(.fn, at: 5)) == [.start(.dictate)])
        #expect(ptt.handle(up(.fn, at: 5.1)) == [], "no cancel yet: it may be the first of two taps")
        #expect(ptt.active == .dictate)
        #expect(ptt.deadline == 5.35)
        #expect(ptt.expire(at: 5.3) == [])
        #expect(ptt.expire(at: 5.35) == [.cancel(.dictate)])
        #expect(ptt.active == nil && ptt.deadline == nil)
    }

    @Test func typingRightAfterATapCancelsAtOnce() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        _ = ptt.handle(up(.fn, at: 0.1))
        #expect(ptt.handle(KeyEvent(.keyDown, at: 0.15)) == [.cancel(.dictate)])
    }

    @Test func tapThenTheOtherKeySwitchesModes() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        _ = ptt.handle(up(.fn, at: 0.1))
        #expect(ptt.handle(down(.rightOption, at: 0.2)) == [.cancel(.dictate), .start(.talk)])
        #expect(ptt.active == .talk)
    }

    @Test func tapThenHoldIsAHoldThatKeepsTheFirstTapsAudio() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        _ = ptt.handle(up(.fn, at: 0.1))
        #expect(ptt.handle(down(.fn, at: 0.2)) == [], "the recording from the first tap goes on")
        #expect(ptt.expire(at: 0.45) == [.confirm(.dictate)])
        #expect(ptt.handle(up(.fn, at: 2)) == [.stop(.dictate)])
        #expect(ptt.locked == nil)
    }

    @Test func secondPressAfterTheWindowIsAPlainHold() {
        var ptt = PushToTalk(doubleTap: 0.35)
        _ = ptt.handle(down(.fn, at: 0))
        _ = ptt.handle(up(.fn, at: 0.1))
        // The timer hasn't fired yet, so the recording is still running: it continues as a fresh hold.
        #expect(ptt.handle(down(.fn, at: 0.4)) == [])
        #expect(ptt.handle(up(.fn, at: 0.45)) == [], "a short press is a first tap again, not a lock")
        #expect(ptt.locked == nil)
        #expect(ptt.expire(at: 0.75) == [.cancel(.dictate)])
    }

    // MARK: Hands-free

    @Test func doubleTapLocksAndTheNextPressStops() {
        var ptt = PushToTalk()
        #expect(doubleTap(.fn, at: 0, into: &ptt) == [.start(.dictate), .lock(.dictate)])
        #expect(ptt.locked == .dictate)
        #expect(ptt.active == .dictate)
        #expect(ptt.handle(down(.fn, at: 10)) == [.stop(.dictate)])
        #expect(ptt.locked == nil)
        #expect(ptt.handle(up(.fn, at: 10.1)) == [], "the release of the stopping tap is swallowed")
        #expect(ptt.active == nil)
    }

    @Test func talkKeyLocksToo() {
        var ptt = PushToTalk()
        #expect(doubleTap(.rightOption, at: 3, into: &ptt) == [.start(.talk), .lock(.talk)])
        #expect(ptt.locked == .talk)
    }

    @Test func escCancelsALockedRecording() {
        var ptt = PushToTalk()
        _ = doubleTap(.fn, at: 0, into: &ptt)
        #expect(ptt.handle(esc(at: 4)) == [.cancel(.dictate)])
        #expect(ptt.locked == nil && ptt.active == nil)
    }

    @Test func typingShortcutsAndTheOtherKeyDontEndALockedRecording() {
        var ptt = PushToTalk()
        _ = doubleTap(.fn, at: 0, into: &ptt)
        #expect(ptt.handle(KeyEvent(.keyDown, at: 1)) == [])
        #expect(ptt.handle(.flagsChanged(keyCode: 55, flags: ModifierFlag.command, at: 2)) == [])
        #expect(ptt.handle(down(.rightOption, at: 3)) == [])
        #expect(ptt.handle(up(.rightOption, at: 3.1)) == [])
        #expect(ptt.locked == .dictate)
    }

    @Test func lockedRecordingStopsAtTheCap() {
        var ptt = PushToTalk(maxLocked: 300)
        _ = doubleTap(.fn, at: 0, into: &ptt)
        #expect(ptt.deadline == 300.28)
        #expect(ptt.expire(at: 299) == [])
        #expect(ptt.expire(at: 300.28) == [.stop(.dictate)])
        #expect(ptt.locked == nil)
    }

    @Test func slowSecondTapDoesNotLock() {
        var ptt = PushToTalk(doubleTap: 0.35)
        _ = ptt.handle(down(.fn, at: 0))
        _ = ptt.handle(up(.fn, at: 0.1))
        #expect(ptt.expire(at: 0.35) == [.cancel(.dictate)])
        #expect(ptt.handle(down(.fn, at: 0.5)) == [.start(.dictate)])
        #expect(ptt.handle(up(.fn, at: 0.6)) == [])
        #expect(ptt.locked == nil)
    }

    // MARK: Bindings

    @Test func rebindMakesOldKeyInertAndNewKeyWork() {
        var ptt = PushToTalk()
        #expect(ptt.rebind(HotkeyBindings(dictate: .rightCommand, talk: .rightOption)) == [])
        #expect(ptt.handle(down(.fn, at: 0)) == [])
        #expect(ptt.handle(up(.fn, at: 1)) == [])
        #expect(ptt.handle(down(.rightCommand, at: 2)) == [.start(.dictate)])
        #expect(ptt.handle(up(.rightCommand, at: 3)) == [.stop(.dictate)])
        #expect(ptt.handle(down(.rightOption, at: 4)) == [.start(.talk)])
    }

    @Test func rebindDuringHoldCancels() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        #expect(ptt.rebind(HotkeyBindings(dictate: .rightControl, talk: .rightOption)) == [.cancel(.dictate)])
        #expect(ptt.handle(up(.fn, at: 1)) == [])
    }

    @Test func rebindAndResetCancelALockedRecording() {
        var ptt = PushToTalk()
        _ = doubleTap(.fn, at: 0, into: &ptt)
        #expect(ptt.rebind(HotkeyBindings(dictate: .rightControl, talk: .rightOption)) == [.cancel(.dictate)])
        _ = doubleTap(.rightControl, at: 1, into: &ptt)
        #expect(ptt.reset() == [.cancel(.dictate)])
        #expect(ptt.reset() == [])
    }

    @Test func rebindToSameBindingsKeepsHold() {
        var ptt = PushToTalk()
        _ = ptt.handle(down(.fn, at: 0))
        #expect(ptt.rebind(.default) == [])
        #expect(ptt.active == .dictate)
    }

    @Test func escKeyCodeBecomesEscape() {
        #expect(KeyEvent.keyDown(keyCode: 53, at: 1).kind == .escape)
        #expect(KeyEvent.keyDown(keyCode: 0, at: 1).kind == .keyDown)
    }

    @Test func liveTranscriptKeepsTheNewestWords() {
        #expect(VoiceCapsule.tail("short", limit: 10) == "short")
        #expect(VoiceCapsule.tail("one two three four", limit: 10) == "…three four")
    }

    @Test(arguments: [
        ("fn", ModifierKey.fn, UInt16(63)),
        ("right_option", .rightOption, 61),
        ("right_command", .rightCommand, 54),
        ("right_control", .rightControl, 62),
    ])
    func brainKeyNamesMapToKeyCodes(name: String, key: ModifierKey, code: UInt16) {
        #expect(ModifierKey(rawValue: name) == key)
        #expect(key.keyCode == code)
        #expect(ModifierFlag.mask(forKeyCode: code) == key.flagMask)
    }

    @Test func everyModifierKeyHasADistinctCode() {
        #expect(Set(ModifierKey.allCases.map(\.keyCode)).count == ModifierKey.allCases.count)
    }

    @Test func unknownKeyNameIsRejectedAndKeepsTheCurrentKey() {
        #expect(ModifierKey(rawValue: "caps_lock") == nil)
        #expect(ModifierKey(rawValue: "left_option") == nil)
        let current = HotkeyBindings.default
        #expect(current.applying(dictateKey: "caps_lock", talkKey: "right_command")
                == HotkeyBindings(dictate: .fn, talk: .rightCommand))
        #expect(current.applying(dictateKey: "nope", talkKey: "nope") == current)
    }

    @Test func bindingBothModesToOneKeyChangesNothing() {
        #expect(HotkeyBindings.default.applying(dictateKey: "right_option", talkKey: "right_option") == .default)
        // fn stays for dictate when its new name is unknown, so talk can't move onto fn.
        #expect(HotkeyBindings.default.applying(dictateKey: "bogus", talkKey: "fn") == .default)
    }

    @Test func swappingKeysIsAllowed() {
        #expect(HotkeyBindings.default.applying(dictateKey: "right_option", talkKey: "fn")
                == HotkeyBindings(dictate: .rightOption, talk: .fn))
    }

    @Test func flagsChangedReadsTheKeysFlag() {
        #expect(KeyEvent.flagsChanged(keyCode: 63, flags: ModifierFlag.function, at: 1)
                == KeyEvent(.modifierChanged(keyCode: 63, isDown: true), at: 1))
        #expect(KeyEvent.flagsChanged(keyCode: 63, flags: 0, at: 2)
                == KeyEvent(.modifierChanged(keyCode: 63, isDown: false), at: 2))
        // Synthetic events carry only the shared bit; that still counts as down.
        #expect(KeyEvent.flagsChanged(keyCode: 61, flags: ModifierFlag.option, at: 3).kind
                == .modifierChanged(keyCode: 61, isDown: true))
    }

    @Test func releasingRightOptionWhileLeftOptionIsHeldIsARelease() {
        // Left and right ⌥ share the option flag; only the per-key bits tell them apart.
        let release = KeyEvent.flagsChanged(keyCode: ModifierKey.rightOption.keyCode,
                                            flags: ModifierFlag.option | leftOptionBit, at: 1)
        #expect(release.kind == .modifierChanged(keyCode: 61, isDown: false))

        var ptt = PushToTalk()
        _ = ptt.handle(.flagsChanged(keyCode: leftOptionCode, flags: ModifierFlag.option | leftOptionBit, at: 0))
        #expect(ptt.handle(.flagsChanged(keyCode: 61, flags: ModifierFlag.option | leftOptionBit | rightOptionBit,
                                         at: 0.1)) == [.start(.talk)])
        #expect(ptt.handle(release) == [.stop(.talk)])
    }
}
