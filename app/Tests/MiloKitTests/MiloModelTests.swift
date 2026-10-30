import Foundation
import Testing
@testable import MiloKit

@Suite struct MiloModelTests {
    let scheduler = ManualScheduler()
    let model: MiloModel

    init() {
        model = MiloModel(scheduler: scheduler)
    }

    @Test func bubbleDurationGrowsWithTextAndCapsAt20Seconds() {
        #expect(MiloModel.bubbleDuration(for: "") == 4)
        #expect(MiloModel.bubbleDuration(for: String(repeating: "a", count: 30)) == 6)
        #expect(MiloModel.bubbleDuration(for: String(repeating: "a", count: 1000)) == 20)
    }

    @Test func bubbleHidesAfterItsDuration() {
        let text = "Hi Niklas! Your standup is at 10."
        let duration = MiloModel.bubbleDuration(for: text)
        model.apply(.heard("what's on my calendar"))
        model.apply(.emotion(.happy))
        model.apply(.bubble(text))
        scheduler.advance(by: duration - 0.01)
        #expect(model.bubble == text)
        scheduler.advance(by: 0.01)
        #expect(model.bubble == nil)
        #expect(model.heard == nil)
        #expect(model.emotion == .neutral)
    }

    @Test func statusShowsInTheBubbleAndHides() {
        model.apply(.status("Mic unavailable"))
        #expect(model.bubble == "Mic unavailable")
        scheduler.advance(by: MiloModel.bubbleDuration(for: "Mic unavailable"))
        #expect(model.bubble == nil)
    }

    @Test func newBubbleRestartsTheTimer() {
        model.apply(.bubble("one"))
        scheduler.advance(by: 3)
        model.apply(.bubble("one two"))
        scheduler.advance(by: 3)
        #expect(model.bubble == "one two")
        scheduler.advance(by: MiloModel.bubbleDuration(for: "one two") - 3)
        #expect(model.bubble == nil)
    }

    @Test func bubbleStaysWhileSpeakingAndHidesOnceIdle() {
        model.apply(.state(.speaking))
        model.apply(.bubble("Hello there."))
        scheduler.advance(by: 60)
        #expect(model.bubble == "Hello there.")
        model.apply(.state(.idle))
        scheduler.advance(by: MiloModel.bubbleDuration(for: "Hello there."))
        #expect(model.bubble == nil)
    }

    @Test func startingToSpeakKeepsAnEarlierBubbleUp() {
        model.apply(.bubble("Earlier note"))
        scheduler.advance(by: 1)
        model.apply(.state(.speaking))
        scheduler.advance(by: 60)
        #expect(model.bubble == "Earlier note")
    }

    @Test func emptyTextHidesTheBubbleAtOnce() {
        model.show("Hi")
        model.show("")
        #expect(model.bubble == nil)
        #expect(scheduler.pendingCount == 0)
    }

    @Test func emotionStaysWhenTheBubbleHidesOutsideIdle() {
        model.apply(.state(.thinking))
        model.apply(.emotion(.thinking))
        model.apply(.bubble("hmm"))
        scheduler.advance(by: 20)
        #expect(model.bubble == nil)
        #expect(model.emotion == .thinking)
    }

    @Test func listeningClearsHeard() {
        model.apply(.heard("old question"))
        model.apply(.state(.listening))
        #expect(model.heard == nil)
        model.apply(.heard("old question"))
        model.apply(.state(.dictating))
        #expect(model.heard == nil)
    }

    @Test func levelResetsOutsideListeningAndSpeaking() {
        for state in [MiloState.listening, .dictating, .speaking] {
            model.apply(.state(state))
            model.apply(.level(0.5))
            #expect(model.level == 0.5)
        }
        model.apply(.state(.transcribing))
        #expect(model.level == 0)
    }

    @Test func aPreviousAnswersTimerDoesNotWipeTheNextQuestion() {
        // Milo finishes an answer; its bubble would hide 4+ s later.
        model.apply(.state(.speaking))
        model.apply(.bubble("It's sunny."))
        model.apply(.state(.idle))
        // The user asks a follow-up straight away.
        scheduler.advance(by: 1)
        model.apply(.state(.listening))
        model.apply(.state(.transcribing))
        model.apply(.heard("and tomorrow?"))
        model.apply(.state(.thinking))
        scheduler.advance(by: 30)
        #expect(model.heard == "and tomorrow?")
        #expect(model.bubble == nil, "the old answer shouldn't stand in for the thinking dots")
    }

    @Test func ignoresEventsThatAreNotItsBusiness() {
        model.apply(.dictation("pasted"))
        model.apply(.uiConfig(dictateKey: "fn", talkKey: "right_option"))
        model.apply(.unknown("confetti"))
        #expect(model.bubble == nil)
        #expect(model.state == .idle)
    }

    @Test func partialLivesFromRecordingThroughTheFinalPass() {
        model.apply(.state(.dictating))
        model.apply(.partial("hello wor"))
        #expect(model.partial == "hello wor")
        model.apply(.partial("hello world"))
        model.apply(.state(.transcribing))
        #expect(model.partial == "hello world", "stays up while the final pass runs")
        model.apply(.state(.idle))
        #expect(model.partial == nil)

        model.apply(.state(.listening))
        model.apply(.partial("what time"))
        model.apply(.partial(""))
        #expect(model.partial == nil)
        model.apply(.partial("what time is it"))
        model.apply(.state(.thinking))
        #expect(model.partial == nil)
    }
}
