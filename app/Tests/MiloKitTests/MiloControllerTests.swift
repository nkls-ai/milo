import Foundation
import Testing
@testable import MiloKit

/// A controller wired to fakes for every port.
private final class Harness {
    let brain = FakeBrainClient()
    let launcher = FakeBrainLauncher()
    let inserter = FakeTextInserter()
    let keys = FakeKeySource()
    let context = FakeContextProvider()
    let accessibility = FakeAccessibility()
    let scheduler = ManualScheduler()
    let model: MiloModel
    let controller: MiloController
    private(set) var bindingChanges: [HotkeyBindings] = []

    init(brainAnswers: Bool = true, trusted: Bool = true, start: Bool = true) {
        brain.answers = brainAnswers
        accessibility.trusted = trusted
        model = MiloModel(scheduler: scheduler)
        controller = MiloController(model: model, brain: brain, launcher: launcher, inserter: inserter,
                                    keys: keys, context: context, accessibility: accessibility,
                                    scheduler: scheduler)
        controller.onBindingsChange = { [unowned self] in bindingChanges.append($0) }
        if start { controller.start() }
    }

    /// Moves the scheduler's clock to `time`, which tests keep equal to the key events' clock.
    func advance(to time: TimeInterval) {
        scheduler.advance(by: time - scheduler.now)
    }

    /// What was sent besides the periodic context.
    var commandsSent: [BrainCommand] {
        brain.sent.filter { if case .context = $0 { false } else { true } }
    }

    var contextsSent: [BrainCommand] {
        brain.sent.filter { if case .context = $0 { true } else { false } }
    }
}

@Suite struct MiloControllerTests {
    // MARK: Startup and shutdown

    @Test func startConnectsAndListensForKeys() {
        let h = Harness()
        #expect(h.brain.started)
        #expect(h.keys.started)
        #expect(h.brain.onEvent != nil && h.brain.onConnectionChange != nil)
        #expect(h.context.onAppSwitch != nil)
        #expect(h.accessibility.prompts == [true])
    }

    @Test func launchesTheBrainOnlyWhenNothingAnswers() {
        #expect(Harness(brainAnswers: true).launcher.starts == 0)
        let h = Harness(brainAnswers: false)
        #expect(h.launcher.starts == 1)
        #expect(h.brain.started)
    }

    @Test func untrustedAccessibilityAsksInTheBubble() throws {
        let h = Harness(trusted: false)
        let bubble = try #require(h.model.bubble)
        #expect(bubble.contains("Accessibility"))
        #expect(bubble.contains("fn"))
        #expect(Harness(trusted: true).model.bubble == nil)
    }

    @Test func stopStopsTheLauncherAndTheContextTimer() {
        let h = Harness(brainAnswers: false)
        h.controller.stop()
        #expect(h.launcher.stops == 1)
        h.scheduler.advance(by: 120)
        #expect(h.contextsSent.isEmpty)
    }

    @Test func restartBrainRestartsTheLauncher() {
        let h = Harness()
        h.controller.restartBrain()
        #expect(h.launcher.restarts == 1)
    }

    // MARK: Connection, mute, context

    @Test func connectingSendsContextAndMuteState() {
        let h = Harness()
        #expect(h.brain.sent.isEmpty)
        h.brain.connect()
        #expect(h.model.connected)
        #expect(h.brain.sent == [.context(app: "Xcode", idleSeconds: 3.5), .mute(false)])
    }

    @Test func toggleMuteSendsAndReconnectResendsIt() {
        let h = Harness()
        h.brain.connect()
        h.brain.clearSent()

        h.controller.toggleMute()
        #expect(h.controller.muted)
        #expect(h.brain.sent == [.mute(true)])

        h.brain.connect(false)
        #expect(!h.model.connected)
        h.context.context = AppContext(app: "Safari", idleSeconds: 1)
        h.brain.clearSent()
        h.brain.connect()
        #expect(h.brain.sent == [.context(app: "Safari", idleSeconds: 1), .mute(true)])

        h.brain.clearSent()
        h.controller.toggleMute()
        #expect(!h.controller.muted)
        #expect(h.brain.sent == [.mute(false)])
    }

    @Test func theDictationStyleComesFromTheBrainAndTheMenuAsksToChangeIt() {
        let h = Harness()
        h.brain.connect()
        #expect(h.controller.dictationStyle == nil)
        h.brain.emit(.dictationStream(.preview))
        #expect(h.controller.dictationStyle == .preview)

        h.brain.clearSent()
        h.controller.setDictationStyle(.type)
        #expect(h.brain.sent == [.setDictationStream(.type)])
        #expect(h.controller.dictationStyle == .preview, "the checkmark moves once the brain confirms")
        h.brain.emit(.dictationStream(.type))
        #expect(h.controller.dictationStyle == .type)
    }

    @Test func losingTheBrainMidAnswerReturnsMiloToIdle() {
        let h = Harness()
        h.brain.connect()
        h.brain.emit(.state(.speaking))
        h.brain.emit(.bubble("Let me tell you about"))
        h.brain.emit(.level(0.8))
        h.brain.connect(false)
        #expect(h.model.state == .idle)
        #expect(h.model.level == 0)
        h.scheduler.advance(by: 20)
        #expect(h.model.bubble == nil)
    }

    @Test func contextTimerSendsPeriodically() {
        let h = Harness()
        h.scheduler.advance(by: 14.9)
        #expect(h.contextsSent.isEmpty)
        h.scheduler.advance(by: 0.1)
        #expect(h.contextsSent == [.context(app: "Xcode", idleSeconds: 3.5)])
        h.scheduler.advance(by: 30)
        #expect(h.contextsSent.count == 3)
    }

    @Test func idleLongerThanTenMinutesMakesMiloDrowsy() {
        let h = Harness()
        h.context.context.idleSeconds = 600
        h.scheduler.advance(by: 15)
        #expect(!h.model.drowsy)
        h.context.context.idleSeconds = 601
        h.scheduler.advance(by: 15)
        #expect(h.model.drowsy)
        h.context.context.idleSeconds = 0.5
        h.scheduler.advance(by: 15)
        #expect(!h.model.drowsy)
    }

    @Test func appSwitchSendsContext() {
        let h = Harness()
        h.context.switchApp(to: "Mail")
        #expect(h.contextsSent == [.context(app: "Mail", idleSeconds: 3.5)])
    }

    // MARK: Brain events

    @Test func dictationInsertsTextAndLeavesTheBubbleAlone() {
        let h = Harness()
        h.brain.emit(.bubble("Hi"))
        h.brain.emit(.dictation("Sounds good, ship it."))
        #expect(h.inserter.inserted == ["Sounds good, ship it."])
        #expect(h.model.bubble == "Hi")

        let quiet = Harness()
        quiet.brain.emit(.dictation("x"))
        #expect(quiet.model.bubble == nil)
    }

    @Test func dictationWithoutAccessibilityLandsOnTheClipboardAndSaysSo() {
        let h = Harness()
        h.accessibility.trusted = false
        h.brain.emit(.dictation("Sounds good, ship it."))
        #expect(h.inserter.inserted.isEmpty)
        #expect(h.inserter.copied == ["Sounds good, ship it."])
        #expect(h.model.bubble == MiloController.pasteBlocked)
    }

    @Test func displayEventsUpdateTheModel() {
        let h = Harness()
        h.brain.emit(.state(.listening))
        h.brain.emit(.level(0.42))
        #expect(h.model.state == .listening)
        #expect(h.model.level == 0.42)
        h.brain.emit(.heard("what's on my calendar"))
        #expect(h.model.heard == "what's on my calendar")
        h.brain.emit(.emotion(.happy))
        #expect(h.model.emotion == .happy)
        h.brain.emit(.bubble("Standup at 10."))
        #expect(h.model.bubble == "Standup at 10.")
        h.brain.emit(.status("Mic unavailable"))
        #expect(h.model.bubble == "Mic unavailable")
        h.brain.emit(.unknown("confetti"))
        #expect(h.inserter.inserted.isEmpty)
        #expect(h.brain.sent.isEmpty)
    }

    @Test func uiConfigRebindsPushToTalk() {
        let h = Harness()
        h.brain.emit(.uiConfig(dictateKey: "right_command", talkKey: "right_option"))
        let expected = HotkeyBindings(dictate: .rightCommand, talk: .rightOption)
        #expect(h.controller.bindings == expected)
        #expect(h.bindingChanges == [expected])

        h.keys.press(.fn, at: 0)
        h.keys.release(.fn, at: 1)
        #expect(h.brain.sent.isEmpty)

        h.keys.press(.rightCommand, at: 2)
        h.keys.release(.rightCommand, at: 3)
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true), .listenStop])
    }

    @Test func uiConfigPicksTheCharacter() {
        let h = Harness()
        #expect(h.model.character == .pip)
        h.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option", character: .classic))
        #expect(h.model.character == .classic)
        h.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option"))
        #expect(h.model.character == .classic, "a missing or unknown character keeps the current one")
    }

    @Test func uiConfigWithTheCurrentKeysChangesNothing() {
        let h = Harness()
        h.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option"))
        h.brain.emit(.uiConfig(dictateKey: "bogus", talkKey: "fn"))
        #expect(h.bindingChanges.isEmpty)
        #expect(h.controller.bindings == .default)
    }

    @Test func uiConfigDuringAHoldCancelsIt() {
        let h = Harness()
        h.keys.press(.fn, at: 0)
        h.brain.emit(.uiConfig(dictateKey: "right_control", talkKey: "right_option"))
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true), .listenCancel])
    }

    // MARK: Push-to-talk

    @Test func holdStartsTentativelyConfirmsAfterMinHoldThenStops() {
        let h = Harness()
        h.keys.press(.rightOption, at: 0)
        #expect(h.brain.sent == [.listenStart(.talk, tentative: true)])
        h.scheduler.advance(by: 0.2)
        #expect(h.brain.sent.count == 1)
        h.scheduler.advance(by: 0.8)
        h.keys.release(.rightOption, at: 1)
        #expect(h.brain.sent == [.listenStart(.talk, tentative: true), .listenConfirm, .listenStop])
        #expect(h.model.handsFree == nil)
    }

    @Test func singleTapCancelsQuietlyOnceTheDoubleTapWindowCloses() {
        let h = Harness()
        h.keys.press(.fn, at: 0)
        h.advance(to: 0.1)
        h.keys.release(.fn, at: 0.1)
        h.advance(to: 0.34)
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true)])
        h.advance(to: 0.36)
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true), .listenCancel])
        #expect(h.scheduler.pendingCount == 1, "only the context timer is left")
    }

    @Test func shortcutDuringAHoldCancels() {
        let h = Harness()
        h.keys.press(.rightOption, at: 0)
        h.keys.type(at: 0.1)
        h.keys.release(.rightOption, at: 0.2)
        #expect(h.brain.sent == [.listenStart(.talk, tentative: true), .listenCancel])
    }

    @Test func doubleTapLocksHandsFreeAndTheNextTapStops() {
        let h = Harness()
        h.keys.press(.fn, at: 0)
        h.keys.release(.fn, at: 0.08)
        h.scheduler.advance(by: 0.2)
        h.keys.press(.fn, at: 0.2)
        h.keys.release(.fn, at: 0.28)
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true), .listenConfirm])
        #expect(h.model.handsFree == .dictate)

        h.scheduler.advance(by: 30)
        h.keys.type(at: 30)
        #expect(h.commandsSent.count == 2, "typing doesn't end a hands-free recording")
        h.keys.press(.fn, at: 30.5)
        h.keys.release(.fn, at: 30.6)
        #expect(h.commandsSent.last == .listenStop)
        #expect(h.model.handsFree == nil)
    }

    @Test func escCancelsHandsFree() {
        let h = Harness()
        h.keys.press(.rightOption, at: 0)
        h.keys.release(.rightOption, at: 0.1)
        h.keys.press(.rightOption, at: 0.2)
        h.keys.release(.rightOption, at: 0.3)
        #expect(h.model.handsFree == .talk)
        h.keys.send(.keyDown(keyCode: KeyEvent.escapeKeyCode, at: 5))
        #expect(h.brain.sent == [.listenStart(.talk, tentative: true), .listenConfirm, .listenCancel])
        #expect(h.model.handsFree == nil)
    }

    @Test func handsFreeStopsByItselfAtTheCapFromUiConfig() {
        let h = Harness()
        h.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option", handsFreeMaxSeconds: 60))
        for (time, down) in [(0, true), (0.1, false), (0.2, true), (0.3, false)] {
            h.advance(to: time)
            if down { h.keys.press(.fn, at: time) } else { h.keys.release(.fn, at: time) }
        }
        h.advance(to: 60.2)
        #expect(h.commandsSent.last == .listenConfirm)
        h.advance(to: 60.4)
        #expect(h.commandsSent.last == .listenStop)
        #expect(h.model.handsFree == nil)
    }

    @Test func losingTheBrainDropsHandsFree() {
        let h = Harness()
        h.brain.connect()
        h.keys.press(.fn, at: 0)
        h.keys.release(.fn, at: 0.1)
        h.keys.press(.fn, at: 0.2)
        h.keys.release(.fn, at: 0.3)
        h.brain.connect(false)
        #expect(h.model.handsFree == nil)
        h.brain.clearSent()
        h.keys.press(.fn, at: 1)
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true)], "a new press starts afresh")
    }

    @Test func otherBindingDuringAHoldIsIgnored() {
        let h = Harness()
        h.keys.press(.fn, at: 0)
        h.keys.press(.rightOption, at: 0.5)
        h.keys.release(.rightOption, at: 0.6)
        h.keys.release(.fn, at: 1)
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true), .listenStop])
    }

    @Test func realFlagsChangedEventsDrivePushToTalk() {
        let h = Harness()
        h.keys.send(.flagsChanged(keyCode: 63, flags: ModifierFlag.function, at: 0))
        h.keys.send(.flagsChanged(keyCode: 63, flags: 0, at: 1))
        #expect(h.brain.sent == [.listenStart(.dictate, tentative: true), .listenStop])
    }
}
