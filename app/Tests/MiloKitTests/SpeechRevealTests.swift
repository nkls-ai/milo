import Foundation
import Testing
@testable import MiloKit

@Suite struct SpeechRevealTests {
    let first = "Just the dentist at four."
    let both = "Just the dentist at four. I'll remind you at half past three."

    private func visible(_ reveal: SpeechReveal, at time: TimeInterval) -> String {
        let cut = reveal.cut(at: time)
        return String(Array(reveal.text)[..<(cut.shown + cut.fresh)])
    }

    @Test func wordsShowAtTheSpeedHeSpeaks() {
        var reveal = SpeechReveal()
        reveal.show(first, speaking: true, at: 10)
        // A word shows as he starts to say it.
        #expect(visible(reveal, at: 10) == "Just")
        #expect(visible(reveal, at: 10.2) == "Just")
        #expect(visible(reveal, at: 10.4) == "Just the")
        #expect(visible(reveal, at: 10.7) == "Just the dentist")
        #expect(visible(reveal, at: 12) == first)
        #expect(reveal.done(at: 12))
    }

    @Test func aWordNeverShowsHalf() {
        var reveal = SpeechReveal()
        reveal.show(both, speaking: true, at: 0)
        for step in 0..<80 {
            let shown = visible(reveal, at: Double(step) * 0.05)
            #expect(shown.isEmpty || both.count == shown.count || both[both.index(both.startIndex, offsetBy: shown.count)] == " ",
                    "cut inside a word: \(shown)")
        }
    }

    @Test func theNewestWordFadesIn() {
        var reveal = SpeechReveal()
        reveal.show(first, speaking: true, at: 0)
        let cut = reveal.cut(at: 0.01)
        #expect(cut.shown == 0 && cut.fresh == 4 && cut.alpha < 1)  // "Just", just arrived
        #expect(reveal.cut(at: SpeechReveal.fade).shown == 4)  // in full once faded in
    }

    @Test func theNextPieceMeansTheLastOneWasHeard() {
        var reveal = SpeechReveal()
        reveal.show(first, speaking: true, at: 0)
        reveal.show(both, speaking: true, at: 0.5)  // early: only a few words were showing
        #expect(visible(reveal, at: 0.5) == first)
        #expect(reveal.settled == first.count)
    }

    @Test func itLearnsHowFastHeTalks() {
        var reveal = SpeechReveal()
        reveal.show(first, speaking: true, at: 0)
        reveal.show(both, speaking: true, at: 2.5)  // 25 characters in 2.5 s: slower than the guess
        #expect(reveal.rate < SpeechReveal.startRate)
        #expect(reveal.rate >= 9)
    }

    @Test func unspokenTextAndTheEndShowEverything() {
        var reveal = SpeechReveal()
        reveal.show("Looking at your calendar…", speaking: false, at: 0)
        #expect(reveal.done(at: 0))
        reveal.show(first, speaking: true, at: 1)
        #expect(!reveal.done(at: 1))
        reveal.finish()
        #expect(reveal.done(at: 1))
    }

    @Test func aNewAnswerStartsFromItsFirstWord() {
        var reveal = SpeechReveal()
        reveal.show("Looking at your calendar…", speaking: false, at: 0)
        reveal.show(first, speaking: true, at: 1)
        #expect(reveal.settled == 0)
        #expect(visible(reveal, at: 1) == "Just")
        #expect(reveal.cut(at: 1).alpha < 1)
    }

    @Test func theModelPacesWhatHeSaysOnly() {
        var time = 100.0
        let model = MiloModel(scheduler: ManualScheduler(), clock: { time })
        model.apply(.state(.speaking))
        model.apply(.bubble(first))
        #expect(model.reveal.paced)
        time += 0.2
        #expect(model.reveal.cut(at: model.now()).shown + model.reveal.cut(at: model.now()).fresh == 4)
        model.apply(.state(.idle))
        #expect(model.reveal.done(at: time))
        model.apply(.status("Mic unavailable"))
        #expect(model.reveal.done(at: time))
    }
}
