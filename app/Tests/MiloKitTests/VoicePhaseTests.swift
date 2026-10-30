import Combine
import Foundation
import Testing
@testable import MiloKit

@Suite struct VoicePhaseTests {
    private func phase(_ state: MiloState, ear: Ear? = nil, handsFree: ListenMode? = nil, pasted: Bool = false,
                       connected: Bool = true, lastMode: ListenMode = .talk, answering: Bool = false) -> VoicePhase? {
        VoicePhase.of(state: state, ear: ear, handsFree: handsFree, pasted: pasted, connected: connected,
                      lastMode: lastMode, answering: answering)
    }

    @Test func eachStateHasOneLook() {
        #expect(phase(.idle) == nil)
        #expect(phase(.listening) == .listening(.talk, handsFree: false))
        #expect(phase(.dictating, handsFree: .dictate) == .listening(.dictate, handsFree: true))
        #expect(phase(.transcribing, lastMode: .dictate) == .transcribing(.dictate))
        #expect(phase(.thinking) == .thinking)
        #expect(phase(.speaking) == nil)
        #expect(phase(.idle, connected: false) == .offline)
    }

    @Test func theKeyWinsOverWhatTheBrainLastSaid() {
        #expect(phase(.idle, ear: .armed(.talk)) == .armed(.talk))
        #expect(phase(.idle, ear: .open(.dictate)) == .listening(.dictate, handsFree: false))
        // The release lands before the brain's own "transcribing".
        #expect(phase(.listening, ear: .caught(.talk)) == .caught(.talk))
        #expect(phase(.speaking, ear: .armed(.talk)) == .armed(.talk))
    }

    @Test func thinkingStepsAsideForAnAnswerOrAQuestion() {
        #expect(phase(.thinking, answering: true) == nil)
    }

    @Test func pastedFollowsDictationOnly() {
        #expect(phase(.idle, ear: .caught(.dictate), pasted: true) == .pasted)
        #expect(phase(.idle, ear: .caught(.talk), pasted: true) == .caught(.talk))
        #expect(phase(.idle, pasted: true) == .pasted)
        #expect(phase(.dictating, pasted: true) == .listening(.dictate, handsFree: false))  // typing as you speak
    }

    @Test func labelsAreShortAndInHisVoice() {
        #expect(VoiceCapsule.label(.armed(.talk), words: false) == nil)
        #expect(VoiceCapsule.label(.caught(.talk), words: false) == "Got it")
        #expect(VoiceCapsule.label(.thinking, words: true) == nil)
        #expect(VoiceCapsule.label(.thinking, words: false) == "Thinking")
        for phase: VoicePhase in [.listening(.talk, handsFree: false), .listening(.dictate, handsFree: true),
                                  .caught(.dictate), .transcribing(.dictate), .pasted, .thinking, .offline] {
            let label = VoiceCapsule.label(phase, words: false) ?? ""
            #expect(label.split(separator: " ").count <= 3, "\(phase): \(label)")
            #expect(!phase.spoken.isEmpty)
        }
    }

    @Test func longThinkingSaysSo() {
        #expect(VoiceCapsule.thinkingLabel(after: 1, words: true) == nil)
        #expect(VoiceCapsule.thinkingLabel(after: 1, words: false) == "Thinking")
        #expect(VoiceCapsule.thinkingLabel(after: 8, words: true) == "Still on it")
        #expect(VoiceCapsule.thinkingLabel(after: 30, words: true) == "Taking a while")
    }

    @Test func theModelKnowsHowLongHeHasBeenThinking() {
        var time = 50.0
        let model = MiloModel(scheduler: ManualScheduler(), clock: { time })
        model.apply(.state(.thinking))
        time = 58
        model.apply(.state(.thinking))  // a repeat doesn't restart the clock
        #expect(model.thinkingSince == 50)
        model.apply(.state(.speaking))
        #expect(model.thinkingSince == nil)
    }

    @Test func theMeterIgnoresRoomNoiseAndFillsForAVoice() {
        #expect(LevelMeter.height(0) == 0)
        #expect(LevelMeter.height(0.03) == 0)
        #expect(LevelMeter.height(0.3) > 0.4)
        #expect(LevelMeter.height(1) == 1)
    }

    @Test func thinkingDotsNeverStandStill() {
        // Over any second, every dot moves.
        for dot in 0..<3 {
            let samples = stride(from: 0.0, to: 1.0, by: 0.05).map { ThinkingDots.wave(at: 1000 + $0, dot: dot) }
            #expect(samples.max()! - samples.min()! > 0.9)
        }
    }
}

@Suite struct EarTests {
    let scheduler = ManualScheduler()
    let model: MiloModel

    init() {
        model = MiloModel(scheduler: scheduler)
        model.connected = true
    }

    @Test func pressHoldReleaseAndTheBeatEnds() {
        model.press(.talk)
        #expect(model.ear == .armed(.talk))
        model.hold(.talk)
        #expect(model.ear == .open(.talk))
        model.release(.talk)
        #expect(model.ear == .caught(.talk))
        scheduler.advance(by: MiloModel.caughtBeat - 0.01)
        #expect(model.ear == .caught(.talk))
        scheduler.advance(by: 0.01)
        #expect(model.ear == nil)
    }

    @Test func aNewPressDuringTheBeatIsNotCutShort() {
        model.press(.talk)
        model.release(.talk)
        scheduler.advance(by: 0.3)
        model.press(.dictate)
        scheduler.advance(by: MiloModel.caughtBeat)
        #expect(model.ear == .armed(.dictate))
    }

    @Test func theBubbleStepsAsideWhileRecording() {
        model.show("Done, it's in your Downloads.")
        model.press(.talk)
        #expect(model.voicePhase?.recording == true)
        model.cancelPress()
        #expect(model.voicePhase == nil)
        #expect(model.bubble != nil)
    }

    @Test func theLevelDoesNotRedrawEveryWindow() {
        var modelChanges = 0, liveChanges = 0
        let a = model.objectWillChange.sink { modelChanges += 1 }
        let b = model.live.objectWillChange.sink { liveChanges += 1 }
        for value in [0.1, 0.4, 0.4, 0.2] { model.apply(.level(value)) }
        #expect(modelChanges == 0)
        #expect(liveChanges == 3)  // the repeat is dropped
        #expect(model.level == 0.2)
        _ = (a, b)
    }

    @Test func aButtonGoesWithItsText() {
        var clicked: [BubbleAction] = []
        model.onBubbleAction = { clicked.append($0) }
        model.show("I need Accessibility.", action: .permissions)
        model.performBubbleAction()
        #expect(clicked == [.permissions])
        model.show("On it.")
        #expect(model.bubbleAction == nil)
    }
}
