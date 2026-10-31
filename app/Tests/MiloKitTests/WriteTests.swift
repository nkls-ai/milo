import Foundation
import Testing
@testable import MiloKit

/// Text Milo writes goes where the user was when they started talking (ADR 33): the field that had the focus at the
/// talk key's press, never his own window, a password field or a terminal. Otherwise it waits to be copied.
@Suite struct WriteTests {
    /// The focus the fake reports, one read at a time: the first read is the key's press, the next the paste.
    final class Probe: FieldProbe {
        var reads: [FocusedField?] = []
        var removes = true
        private(set) var removed: [(String, Int)] = []

        func focused(_ done: @escaping (FocusedField?) -> Void) {
            done(reads.isEmpty ? nil : reads.removeFirst())
        }

        func remove(_ text: String, from field: Int, _ done: @escaping (Bool) -> Void) {
            removed.append((text, field))
            done(removes)
        }
    }

    static let mail = FocusedField(pid: 41, app: "Mail", bundle: "com.apple.mail", field: 7, role: "AXWebArea")
    static let email = "Hi Anna,\n\nI'm running ten minutes late.\n\nNiklas"

    private func writing(_ probe: Probe, inserter: FakeTextInserter = FakeTextInserter(), trusted: Bool = true)
        -> WriteRequests {
        WriteRequests(probe: probe, inserter: inserter, trusted: { trusted })
    }

    private func call(_ w: WriteRequests, _ op: String, _ args: [String: JSONValue]) -> [AppOutcome] {
        var outcomes: [AppOutcome] = []
        w.handle(op: op, args: .object(args)) { outcomes.append($0) }
        return outcomes
    }

    private func write(_ w: WriteRequests, _ text: String = WriteTests.email, paste: Bool = true) -> [AppOutcome] {
        call(w, "text.write", ["text": .string(text), "paste": .bool(paste)])
    }

    private static func kept(_ why: String, _ app: String = "") -> [AppOutcome] {
        [.success(.object(["pasted": .bool(false), "why": .string(why), "app": .string(app)]))]
    }

    // MARK: The clipboard

    @Test func aCopyStaysOnTheClipboardWithoutAKeyPressOrAField() {
        let inserter = FakeTextInserter()
        let w = writing(Probe(), inserter: inserter, trusted: false)
        let link = "https://github.com/NiklasDob/milo"
        #expect(call(w, "text.copy", ["text": .string(link)]) == [.success(.object(["copied": .bool(true)]))])
        #expect(inserter.copied == [link] && inserter.inserted.isEmpty, "copied, never pasted")
        guard case .failure = call(w, "text.copy", ["text": .string("  ")]).first else {
            Issue.record("nothing to copy is a failure")
            return
        }
    }

    // MARK: Where it may go

    @Test func theFieldFromTheKeyPressGetsItThroughDictationsPaste() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        let inserter = FakeTextInserter()
        let w = writing(probe, inserter: inserter)
        var pasted: [String] = []
        w.onPasted = { pasted.append($0) }
        w.capture()
        #expect(write(w) == [.success(.object(["pasted": .bool(true), "app": .string("Mail"), "field": .string("f-7")]))])
        #expect(inserter.inserted == [Self.email], "line breaks and all, through the same ⌘V as dictation")
        #expect(pasted == [Self.email])
    }

    @Test func focusThatMovedSinceTheKeyPressGetsNothing() {
        let probe = Probe()
        var slack = Self.mail
        slack.pid = 52
        slack.app = "Slack"
        var otherField = Self.mail
        otherField.field = 8
        for now in [slack, otherField] {
            probe.reads = [Self.mail, now]
            let inserter = FakeTextInserter()
            let w = writing(probe, inserter: inserter)
            var kept: [String] = []
            w.onKept = { kept.append($0) }
            w.capture()
            #expect(write(w) == Self.kept("moved", now.app))
            #expect(inserter.inserted.isEmpty && kept == [Self.email], "it waits to be copied")
        }
    }

    @Test func passwordFieldsTerminalsAndNoFieldAtAllGetNothing() {
        func verdict(_ field: FocusedField) -> PasteTarget.Verdict { PasteTarget.verdict(keyDown: field, now: field) }
        var field = Self.mail
        field.secure = true
        #expect(verdict(field) == .keep("secure"))
        field = Self.mail
        field.label = "card number"
        #expect(verdict(field) == .keep("secure"))
        field = FocusedField(pid: 9, app: "Terminal", bundle: "com.apple.Terminal", field: 1)
        #expect(verdict(field) == .keep("terminal"))
        field = FocusedField(pid: 9, app: "iTerm2", bundle: "com.googlecode.iterm2", field: 1)
        #expect(verdict(field) == .keep("terminal"))
        // The terminal pane of an editor: xterm.js labels its input.
        field = FocusedField(pid: 10, app: "Code", bundle: "com.microsoft.VSCode", field: 2, label: "terminal input")
        #expect(verdict(field) == .keep("terminal"))
        field = FocusedField(pid: 11, app: "T3 Code (Beta)", bundle: "", field: 3, label: "terminal 1, zsh")
        #expect(verdict(field) == .keep("terminal"))
        field = FocusedField(pid: 10, app: "Code", bundle: "com.microsoft.VSCode", field: 4, label: "editor content")
        #expect(verdict(field) == .paste, "the editor itself is a text field like any other")
        field = FocusedField(pid: 12, app: "Finder", field: 5, role: "AXList", editable: false)
        #expect(verdict(field) == .keep("no_field"))
        #expect(PasteTarget.verdict(keyDown: nil, now: Self.mail) == .keep("no_field"))
    }

    @Test func linesGoOnlyIntoAFieldThatPositivelyTakesTyping() {
        // A terminal Milo doesn't know: a text area whose value Accessibility won't let anyone set.
        let unknown = FocusedField(pid: 13, app: "NewTerm", bundle: "com.example.newterm", field: 1, settable: false)
        #expect(PasteTarget.verdict(keyDown: unknown, now: unknown, lines: true) == .keep("no_field"))
        #expect(PasteTarget.verdict(keyDown: unknown, now: unknown, lines: false) == .paste, "one line runs nothing")
        #expect(PasteTarget.verdict(keyDown: Self.mail, now: Self.mail, lines: true) == .paste)
    }

    @Test func aKeyPressIsUsedOnceAndNotLongAfter() {
        let probe = Probe()
        var clock = Date(timeIntervalSince1970: 0)
        let inserter = FakeTextInserter()
        let w = WriteRequests(probe: probe, inserter: inserter, trusted: { true }, now: { clock })
        probe.reads = [Self.mail, Self.mail, Self.mail]
        w.capture()
        _ = write(w)
        #expect(write(w) == Self.kept("no_field", "Mail"), "a second text needs a new press")
        probe.reads = [Self.mail, Self.mail]
        w.capture()
        clock += WriteRequests.capturedFor + 1
        #expect(write(w) == Self.kept("no_field", "Mail"))
        #expect(inserter.inserted.count == 1)
    }

    @Test func noLineBreakAtTheEndGoesIn() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        let inserter = FakeTextInserter()
        let w = writing(probe, inserter: inserter)
        w.capture()
        _ = write(w, "ls -la\n\n")
        #expect(inserter.inserted == ["ls -la"])
    }

    @Test func milosOwnWindowIsNeverTheTarget() {
        let milo = FocusedField(pid: 1, app: "Milo", field: 1, milo: true)
        #expect(PasteTarget.verdict(keyDown: milo, now: milo) == .keep("here"))
        #expect(PasteTarget.verdict(keyDown: Self.mail, now: milo) == .keep("here"), "typed in his window")
    }

    @Test func textTheBrainHoldsBackIsOnlyOfferedToCopy() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        let inserter = FakeTextInserter()
        let w = writing(probe, inserter: inserter)
        var kept: [String] = []
        w.onKept = { kept.append($0) }
        w.capture()
        #expect(write(w, paste: false) == Self.kept("held"))
        #expect(inserter.inserted.isEmpty && kept == [Self.email])
    }

    @Test func withoutAccessibilityNothingIsPastedIntoTheVoid() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        let inserter = FakeTextInserter()
        let w = writing(probe, inserter: inserter, trusted: false)
        w.capture()
        #expect(write(w) == Self.kept("blocked"))
        #expect(inserter.inserted.isEmpty)
    }

    // MARK: Undo

    @Test func undoTakesThePastedTextBackOutOfItsField() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        let w = writing(probe)
        w.capture()
        _ = write(w)
        #expect(call(w, "text.unwrite", ["field": "f-7", "text": .string(Self.email)]) ==
            [.success(.object(["removed": .bool(true)]))])
        #expect(probe.removed.map(\.1) == [7] && probe.removed.map(\.0) == [Self.email])
    }

    @Test func aFieldThatChangedSinceGetsTheAppsOwnUndoInPlainWords() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        probe.removes = false
        let w = writing(probe)
        w.capture()
        _ = write(w)
        #expect(call(w, "text.unwrite", ["field": "f-7", "text": .string(Self.email)]) ==
            [.failure("The text there changed since, so I left it. Press ⌘Z in Mail to take it back.")])
        #expect(call(w, "text.unwrite", ["field": "nonsense", "text": "x"]) ==
            [.failure("The text there changed since, so I left it. Press ⌘Z there to take it back.")])
    }

    // MARK: The bubble and the controller

    @Test func keptTextGetsCopyUnderTheLineMiloSaysAboutIt() {
        let model = MiloModel(scheduler: ManualScheduler())
        var copied: [String] = []
        model.copy = { copied.append($0) }
        model.offerCopy(Self.email)
        model.apply(.bubble("I don't paste into a terminal,"))
        #expect(model.bubbleAction == .copy(Self.email))
        model.apply(.bubble("I don't paste into a terminal, so it's in my window to copy."))
        #expect(model.bubbleAction == .copy(Self.email), "the same line, grown as he speaks it")
        model.performBubbleAction()
        #expect(copied == [Self.email])
        #expect(model.bubble == MiloModel.copied)
        model.apply(.bubble("Something else."))
        #expect(model.bubbleAction == nil, "offered once")
    }

    @Test func theTalkKeyRemembersTheFocusAndTextOpsGoToWriting() {
        let probe = Probe()
        probe.reads = [Self.mail, Self.mail]
        let inserter = FakeTextInserter()
        let brain = FakeBrainClient()
        let keys = FakeKeySource()
        let model = MiloModel(scheduler: ManualScheduler())
        let controller = MiloController(
            model: model, brain: brain, launcher: FakeBrainLauncher(), inserter: inserter, keys: keys,
            context: FakeContextProvider(), accessibility: FakeAccessibility(), scheduler: ManualScheduler(),
            connections: FakeConnections(), writing: WriteRequests(probe: probe, inserter: inserter, trusted: { true }))
        controller.start()
        keys.press(.fn, at: 0)  // dictation doesn't move the target
        #expect(controller.writing?.keyDown == nil)
        keys.release(.fn, at: 0.1)
        keys.press(.rightOption, at: 1)
        #expect(controller.writing?.keyDown == Self.mail)
        brain.emit(.appRequest(id: "a1", op: "text.write", args: .object(["text": .string("Hi"), "paste": .bool(true)])))
        #expect(inserter.inserted == ["Hi"])
        #expect(brain.sent.contains(.appResponse(id: "a1", outcome: .success(.object([
            "pasted": .bool(true), "app": .string("Mail"), "field": .string("f-7"),
        ])))))
        #expect(model.pasted, "the same Pasted as dictation")
    }

    // MARK: The card

    @Test func theCardSaysWhereItWentAndAClickGoesThere() {
        let pasted = ActionDone(kind: .written, title: "Hi Anna,", app: "Mail", undo: "w-1")
        let kept = ActionDone(kind: .written, title: "Hi Anna,")
        #expect(DoneCardText.line(pasted, now: Date()) == "In Mail")
        #expect(DoneCardText.line(kept, now: Date()) == "Ready to copy")
        #expect(DonePlace.of(pasted) == .app("Mail"))
        #expect(DonePlace.of(kept) == .conversation)
    }
}
