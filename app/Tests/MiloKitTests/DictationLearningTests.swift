import Foundation
import Testing
@testable import MiloKit

/// A focused field the test types into. `nil` value: nothing readable is focused (a password field, another app).
final class FakeFocusedText: FocusedTextReader {
    var field = 1
    var value: String?
    var caret = 0
    private(set) var reads = 0

    func read(_ done: @escaping (FocusedText?) -> Void) {
        reads += 1
        done(value.map { FocusedText(field: field, value: $0, caret: caret) })
    }

    /// Milo's Cmd-V landing: the text goes in at the caret.
    func paste(_ text: String) {
        let field = (value ?? "") as NSString
        value = field.replacingCharacters(in: NSRange(location: caret, length: 0), with: text)
        caret += (text as NSString).length
    }

    /// The user's edit: `old` becomes `new`, the first time it occurs.
    func edit(_ old: String, _ new: String) {
        value = value?.replacingOccurrences(of: old, with: new, options: .literal,
                                            range: value?.range(of: old))
    }
}

final class FakeWords: WordList {
    let words: Set<String>
    init(_ words: Set<String> = ["their", "there", "cat", "car", "the", "big", "huge"]) { self.words = words }
    func isWord(_ word: String) -> Bool { words.contains(word.lowercased()) }
}

private func fixes(_ pasted: String, _ edited: String, words: WordList = FakeWords()) -> [String] {
    CorrectionDiff.fixes(pasted: pasted, edited: edited, words: words).map { "\($0.heard) -> \($0.meant)" }
}

@Suite struct CorrectionDiffTests {
    @Test func aNameIsLearnedWithTheRestOfIt() {
        #expect(fixes("I use Cloud Code every day.", "I use Claude Code every day.") == ["Cloud Code -> Claude Code"])
        #expect(fixes("Hi Nicholas, thanks for the notes.", "Hi Niklas, thanks for the notes.") == ["Nicholas -> Niklas"])
        #expect(fixes("Ask Anna and Nicholas Smith.", "Ask Anna and Niklas Smith.") == ["Nicholas Smith -> Niklas Smith"])
    }

    @Test func severalFixesInOnePaste() {
        #expect(fixes("Tell Nicholas the Cloud Code demo is on teh list.",
                      "Tell Niklas the Claude Code demo is on the list.")
                == ["Nicholas -> Niklas", "Cloud Code -> Claude Code", "teh -> the"])
    }

    @Test func aFixAtTheEndStillCountsWhenTheUserTypesOn() {
        #expect(fixes("Thanks Nicholas", "Thanks Niklas, see you soon") == ["Nicholas -> Niklas"])
        #expect(fixes("Nicholas said yes", "So Niklas said yes") == ["Nicholas -> Niklas"])
    }

    @Test func casingAndJoinedWords() {
        #expect(fixes("push it to github today", "push it to GitHub today") == ["github -> GitHub"])
        #expect(fixes("ask milo now", "ask Milo now") == ["milo -> Milo"])
        #expect(fixes("on my Mac Book", "on my MacBook") == ["Mac Book -> MacBook"])
    }

    @Test func aCapitalAtASentenceStartIsNotAFix() {
        #expect(fixes("we met and the plan is set", "we met. The plan is set") == [])
        #expect(fixes("the plan is set", "The plan is set") == [])
        #expect(fixes("Okay. The plan is set", "Okay, the plan is set") == [])
    }

    @Test func rewritesAndNewThoughtsTeachNothing() {
        #expect(fixes("Let's meet at the station tomorrow morning", "Can we do lunch on Friday instead") == [])
        #expect(fixes("See you at noon", "See you at noon. Also bring the cake, Claude") == [])
        #expect(fixes("First thing. Second thing about Nicholas.", "First thing.") == [])
        #expect(fixes("See you at noon", "") == [])
        #expect(fixes("It is a big deal", "It is a huge deal") == [], "spelled differently: a new word, not a mishearing")
    }

    @Test func changesOfMindAreNotLearned() {
        #expect(fixes("I think their right", "I think there right") == [], "both are words: grammar, fits this sentence")
        #expect(fixes("the cat is here", "the car is here") == [])
        #expect(fixes("See you on Monday", "See you on Sunday") == [])
        #expect(fixes("meet at 15 sharp", "meet at 16 sharp") == [])
        #expect(fixes("teh plan", "the plan") == ["teh -> the"], "not a word: a misspelling")
    }

    @Test func punctuationAloneIsNoFix() {
        #expect(fixes("Hello Claude Code", "Hello, Claude Code!") == [])
    }

    @Test func atMostEightFixes() {
        let names = (0..<10).map { "Nicholas\($0)x" }
        let fixed = names.map { $0.replacingOccurrences(of: "Nicholas", with: "Niklas") }
        let pasted = names.joined(separator: " met the team and "), edited = fixed.joined(separator: " met the team and ")
        #expect(CorrectionDiff.fixes(pasted: pasted, edited: edited, words: FakeWords()).count == CorrectionDiff.maxFixes)
    }

    @Test func distanceAndSimilarity() {
        #expect(CorrectionDiff.distance(Array("cloud"), Array("claude")) == 2)
        #expect(CorrectionDiff.distance(Array("teh"), Array("the")) == 1)
        #expect(CorrectionDiff.distance(Array(""), Array("the")) == 3)
        #expect(CorrectionDiff.similar("Cloud", "Claude"))
        #expect(CorrectionDiff.similar("Nicholas", "Niklas"))
        #expect(!CorrectionDiff.similar("big", "huge"))
        #expect(!CorrectionDiff.similar("Cloud", "x"))
    }
}

@Suite struct PastedSpanTests {
    @Test func thePasteMustSitBeforeTheCaret() throws {
        let value = "Dear Anna, I use Cloud Code daily. Best"
        let caret = (value as NSString).range(of: " Best").location
        let span = try #require(PastedSpan(pasted: " I use Cloud Code daily.", value: value, caret: caret))
        #expect(span.pasted == "I use Cloud Code daily.")
        #expect(PastedSpan(pasted: "something else", value: value, caret: caret) == nil)
        #expect(PastedSpan(pasted: "Best", value: value, caret: 2) == nil)
    }

    @Test func itIsFoundAgainAfterEditsInsideAndElsewhere() throws {
        let value = "Dear Anna,\nI use Cloud Code daily.\nBest, Niklas"
        let caret = (value as NSString).range(of: "\nBest").location
        let span = try #require(PastedSpan(pasted: "I use Cloud Code daily.", value: value, caret: caret))
        let edited = "Dear Anna,\nI use Claude Code daily.\nBest, Niklas"
        #expect(span.find(in: edited)?.text == "I use Claude Code daily.")
        let more = "Subject: hi\n\n" + edited + "\n\nPS: call me"
        #expect(span.find(in: more)?.text == "I use Claude Code daily.")
    }

    @Test func aPasteAtTheEndTakesWhatIsTypedAfterIt() throws {
        let span = try #require(PastedSpan(pasted: "Thanks Nicholas", value: "Thanks Nicholas", caret: 15))
        #expect(span.find(in: "Thanks Niklas, see you")?.text == "Thanks Niklas, see you")
        #expect(span.find(in: "")?.text == "")
        let novel = "Thanks Niklas" + String(repeating: " and more", count: 40)
        #expect(span.find(in: novel) == nil, "far longer than the paste: not the same words any more")
    }

    @Test func anEditToAnAnchorLosesTheSpan() throws {
        let value = "Hello there, I use Cloud Code daily. Bye now"
        let caret = (value as NSString).range(of: " Bye").location
        let span = try #require(PastedSpan(pasted: "I use Cloud Code daily.", value: value, caret: caret))
        #expect(span.find(in: value.replacingOccurrences(of: "Hello there,", with: "Hi,")) == nil)
    }

    @Test func aPasteRightAtTheEndJoinsTheSpan() throws {
        var value = "Hi Nicholas,"
        var span = try #require(PastedSpan(pasted: "Hi Nicholas,", value: value, caret: 12))
        value += " thanks Nicholas."
        let joined = span.extend(with: " thanks Nicholas.", value: value, caret: (value as NSString).length)
        #expect(joined && span.pasted == "Hi Nicholas, thanks Nicholas.")
        let elsewhere = span.extend(with: "Hi", value: "Hi " + value, caret: 2)
        #expect(!elsewhere)
    }
}

/// A watcher on fakes: the test pastes, edits and moves time.
private final class Watching {
    let field = FakeFocusedText()
    let scheduler = ManualScheduler()
    let watcher: PasteWatcher
    private(set) var sent: [[String]] = []

    init(value: String = "") {
        field.value = value
        field.caret = (value as NSString).length
        watcher = PasteWatcher(reader: field, words: FakeWords(), scheduler: scheduler)
        watcher.onFixes = { [unowned self] in sent.append($0.map { "\($0.heard) -> \($0.meant)" }) }
    }

    func paste(_ text: String) {
        field.paste(text)
        watcher.pasted(text)
    }
}

@Suite struct PasteWatcherTests {
    @Test func theFixIsSentOnceTheWindowEnds() {
        let w = Watching(value: "Dear Anna, ")
        w.paste("I use Cloud Code daily.")
        w.scheduler.advance(by: 5)
        w.field.edit("Cloud", "Claude")
        w.scheduler.advance(by: 30)
        #expect(w.sent == [], "still watching: the user may fix more")
        w.scheduler.advance(by: 15)
        #expect(w.sent == [["Cloud Code -> Claude Code"]])
        let reads = w.field.reads
        w.scheduler.advance(by: 60)
        #expect(w.field.reads == reads, "no reads after the watch")
        #expect(w.scheduler.pendingCount == 0)
    }

    @Test func atMostOneReadEveryHalfSecond() {
        let w = Watching()
        w.paste("Hello Nicholas")
        w.scheduler.advance(by: 60)
        #expect(w.field.reads <= 1 + Int(45 / 0.5))
    }

    @Test func sendingTheMessageEndsTheWatchWithTheLastWords() {
        let w = Watching()
        w.paste("Thanks Nicholas")
        w.scheduler.advance(by: 2)
        w.field.edit("Nicholas", "Niklas")
        w.scheduler.advance(by: 1)
        w.field.value = ""  // Enter in a chat app: the field is empty again
        w.field.caret = 0
        w.scheduler.advance(by: 1)
        #expect(w.sent == [["Nicholas -> Niklas"]])
    }

    @Test func movingToAnotherFieldEndsTheWatch() {
        let w = Watching()
        w.paste("Thanks Nicholas")
        w.scheduler.advance(by: 1)
        w.field.edit("Nicholas", "Niklas")
        w.scheduler.advance(by: 1)
        w.field.field = 2
        w.scheduler.advance(by: 1)
        #expect(w.sent == [["Nicholas -> Niklas"]])
    }

    @Test func nothingIsReadWhereItMayNotBe() {
        let w = Watching()
        w.field.value = nil  // a password field
        w.watcher.pasted("Thanks Nicholas")
        w.scheduler.advance(by: 60)
        #expect(w.sent == [] && w.field.reads == 1)
        #expect(w.scheduler.pendingCount == 0)
    }

    @Test func anUntouchedPasteSendsNothing() {
        let w = Watching()
        w.paste("Thanks Nicholas")
        w.scheduler.advance(by: 60)
        #expect(w.sent == [])
    }

    @Test func typedPhrasesAreWatchedAsOne() {
        let w = Watching()
        w.paste("Hi Nicholas,")
        w.scheduler.advance(by: 2)
        w.paste(" the Cloud Code demo is ready.")
        w.scheduler.advance(by: 2)
        w.field.edit("Nicholas", "Niklas")
        w.field.edit("Cloud", "Claude")
        w.scheduler.advance(by: 46)
        #expect(w.sent == [["Nicholas -> Niklas", "Cloud Code -> Claude Code"]])
    }

    @Test func aPasteSomewhereElseEndsTheLastWatch() {
        let w = Watching()
        w.paste("Thanks Nicholas")
        w.scheduler.advance(by: 1)
        w.field.edit("Nicholas", "Niklas")
        w.scheduler.advance(by: 1)
        w.field.field = 2
        w.field.value = ""
        w.field.caret = 0
        w.paste("Hello there")
        w.scheduler.advance(by: 1)
        #expect(w.sent == [["Nicholas -> Niklas"]])
    }

    @Test func stopForgetsTheWatch() {
        let w = Watching()
        w.paste("Thanks Nicholas")
        w.scheduler.advance(by: 1)
        w.field.edit("Nicholas", "Niklas")
        w.watcher.stop()
        w.scheduler.advance(by: 60)
        #expect(w.sent == [] && w.scheduler.pendingCount == 0)
    }
}

@Suite struct ControllerLearningTests {
    private func harness() -> (FakeBrainClient, FakeFocusedText, ManualScheduler, MiloController) {
        let brain = FakeBrainClient(), field = FakeFocusedText(), scheduler = ManualScheduler()
        field.value = ""
        let controller = MiloController(
            model: MiloModel(scheduler: scheduler), brain: brain, launcher: FakeBrainLauncher(),
            inserter: FakeTextInserter(), keys: FakeKeySource(), context: FakeContextProvider(),
            accessibility: FakeAccessibility(), scheduler: scheduler,
            pasteWatcher: PasteWatcher(reader: field, words: FakeWords(), scheduler: scheduler))
        controller.start()
        brain.connect()
        return (brain, field, scheduler, controller)
    }

    private func settings(learn: Bool) throws -> BrainEvent {
        let json = """
        {"type": "settings", "settings": [{"section": "dictation", "key": "learn", "value": \(learn), "options": [],
         "labels": [], "live": true}], "restart": false, "error": ""}
        """
        return try JSONDecoder().decode(BrainEvent.self, from: Data(json.utf8))
    }

    private func dictate(_ text: String, into field: FakeFocusedText, brain: FakeBrainClient) {
        field.paste(text)  // the fake inserter doesn't type; the field gets it here
        brain.emit(.dictation(text))
    }

    @Test func fixesGoToTheBrainWhenLearningIsOn() throws {
        let (brain, field, scheduler, controller) = harness()
        brain.emit(try settings(learn: true))
        #expect(controller.learnsFromFixes)
        dictate("Thanks Nicholas", into: field, brain: brain)
        scheduler.advance(by: 1)
        field.edit("Nicholas", "Niklas")
        scheduler.advance(by: 50)
        #expect(brain.sent.contains(.dictationFixed([DictationFix(heard: "Nicholas", meant: "Niklas")])))
    }

    @Test func nothingIsReadWhenLearningIsOffOrUnknown() throws {
        let (brain, field, scheduler, controller) = harness()
        #expect(!controller.learnsFromFixes, "no settings from the brain yet")
        dictate("Thanks Nicholas", into: field, brain: brain)
        brain.emit(try settings(learn: false))
        dictate(" again", into: field, brain: brain)
        scheduler.advance(by: 50)
        #expect(field.reads == 0)
    }
}
