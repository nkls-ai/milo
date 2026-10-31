import Foundation
import Testing
@testable import MiloKit

/// A screen controller wired to fakes, behind a full MiloController so events take the real route.
private final class Rig {
    let brain = FakeBrainClient()
    let reader = FakeScreenReader()
    let hands = FakeHandsExecutor()
    let input = FakeInputSource()
    let hotkey = FakeHotkey()
    let cursor = FakeCursor()
    let windows = FakeWindowWatcher()
    let scheduler = ManualScheduler()
    let model: MiloModel
    let screen: ScreenController
    let controller: MiloController
    var clock: TimeInterval = 100

    init() {
        model = MiloModel(scheduler: scheduler)
        let ports = ScreenPorts(reader: reader, hands: hands, input: input, hotkey: hotkey, cursor: cursor,
                                windows: windows)
        var now: () -> TimeInterval = { 0 }
        screen = ScreenController(model: model, brain: brain, ports: ports, now: { now() },
                                  toAppKit: { CGPoint(x: $0.x, y: 1000 - $0.y) }, scheduler: scheduler)
        controller = MiloController(model: model, brain: brain, launcher: FakeBrainLauncher(),
                                    inserter: FakeTextInserter(), keys: FakeKeySource(), context: FakeContextProvider(),
                                    accessibility: FakeAccessibility(), scheduler: scheduler, screen: screen)
        now = { [unowned self] in clock }
        controller.start()
        brain.clearSent()
    }

    var sent: [BrainCommand] {
        brain.sent.filter { if case .context = $0 { false } else { true } }
    }

    /// Starts a session with the pointer resting at (0, 0) a while ago. `borrowed`: the user lent the mouse.
    func startSession(borrowed: Bool = false) {
        brain.emit(.handsSession(true))
        if borrowed { brain.emit(.handsBorrow(on: true, what: "mouse")) }
        input.send(UserInput(.mouseMoved(x: 0, y: 0), at: clock))
        clock += 1
    }

    /// describe answers with a click on a button at (600, 400) in a window of pid 42.
    func describesAButton() {
        hands.results["describe"] = .success([
            "app": "TextEdit", "title": "Bold", "point": .object(["x": 600, "y": 400]), "pid": 42,
            "window": .object(["x": 100, "y": 50, "width": 800, "height": 600]),
        ])
    }
}

@Suite struct ScreenControllerTests {
    @Test func aLookRequestIsAnsweredWithTheCapture() {
        let r = Rig()
        r.brain.emit(.lookRequest(id: "look-1", mode: "window"))
        #expect(r.reader.requests == [false])
        #expect(r.sent == [.lookResult(id: "look-1", r.reader.capture)])
    }

    @Test func theEyeFollowsLooking() {
        let r = Rig()
        r.brain.emit(.looking(true))
        #expect(r.model.looking)
        r.brain.emit(.looking(false))
        #expect(!r.model.looking)
    }

    @Test func whatsThisCapturesTheSelectionAndAsks() {
        let r = Rig()
        r.reader.capture = ScreenCapture(app: "Mail", selection: "Pay customs here")
        r.hotkey.press()
        #expect(r.reader.requests == [true])
        #expect(r.sent == [.whatsThis(ScreenCapture(app: "Mail", selection: "Pay customs here"))])
    }

    @Test func uiConfigRegistersTheShortcut() {
        let r = Rig()
        r.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option", whatsThisKey: "ctrl+option+m"))
        r.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option", whatsThisKey: ""))
        r.brain.emit(.uiConfig(dictateKey: "fn", talkKey: "right_option"))
        #expect(r.hotkey.registered == [KeyCombo("ctrl+option+m"), nil], "nil from an older brain keeps it")
    }

    @Test func handsRequestsRunAndAnswer() {
        let r = Rig()
        r.brain.emit(.handsRequest(id: "hands-1", tool: "click", args: ["x": 1, "y": 2]))
        r.hands.result = .failure(HandsFailure("There is no element e9."))
        r.brain.emit(.handsRequest(id: "hands-2", tool: "ax_press", args: ["element": "e9"]))
        #expect(r.hands.performed == ["click", "ax_press"])
        #expect(r.sent == [.handsResult(id: "hands-1", ok: true, result: ["text": "done"]),
                           .handsResult(id: "hands-2", ok: false, result: [:], error: "There is no element e9.")])
    }

    @Test func theSessionShowsTheFrameAndWatchesInput() {
        let r = Rig()
        r.brain.emit(.handsSession(true))
        #expect(r.model.handsActive && r.input.running)
        r.brain.emit(.flyTo(ScreenPoint(x: 812, y: 430)))
        #expect(r.model.flyTarget == CGPoint(x: 812, y: 570))
        r.brain.emit(.handsSession(false))
        #expect(!r.model.handsActive && !r.input.running && r.model.flyTarget == nil)
    }

    @Test func whileTheMouseIsLentRealInputStopsTheSessionAtOnce() {
        let r = Rig()
        r.startSession(borrowed: true)
        r.hands.hold = true
        r.brain.emit(.handsRequest(id: "hands-1", tool: "run_applescript", args: ["script": "delay 20"]))
        r.input.send(UserInput(.key, at: r.clock))
        #expect(r.sent == [.handsStop(reason: "user")])
        #expect(r.hands.cancels == 1 && !r.model.handsActive && !r.input.running)
    }

    @Test func escSaysEscape() {
        let r = Rig()
        r.startSession()
        r.input.send(UserInput(.escape, at: r.clock))
        #expect(r.sent == [.handsStop(reason: "escape")])
    }

    @Test func milosOwnEventsDontStopHim() {
        let r = Rig()
        r.startSession(borrowed: true)
        r.brain.emit(.handsRequest(id: "hands-1", tool: "click", args: ["x": 600, "y": 400]))
        r.input.send(UserInput(.mouseMoved(x: 600, y: 400), at: r.clock + 0.1))
        r.input.send(UserInput(.mouseDown, at: r.clock + 0.1, synthetic: true))
        #expect(r.sent == [.handsResult(id: "hands-1", ok: true, result: ["text": "done"])])
        #expect(r.model.handsActive)
    }

    @Test func afterAStopActionsAreRefusedUntilTheBrainEndsTheSession() {
        let r = Rig()
        r.startSession(borrowed: true)
        r.input.send(UserInput(.mouseDown, at: r.clock))
        r.brain.emit(.handsRequest(id: "hands-9", tool: "type", args: ["text": "x"]))
        #expect(r.hands.performed.isEmpty)
        #expect(r.sent.last == .handsResult(id: "hands-9", ok: false, result: [:], error: "stopped"))
        r.brain.emit(.handsSession(false))
        r.brain.emit(.handsRequest(id: "hands-10", tool: "list_apps", args: [:]))
        #expect(r.hands.performed == ["list_apps"], "the next task works again")
    }

    @Test func answeringAQuestionWithTheMouseDoesntStopTheSession() {
        let r = Rig()
        r.startSession(borrowed: true)
        r.brain.emit(.confirm(id: "q1", question: "Send it?"))
        #expect(r.model.question == PendingQuestion(id: "q1", text: "Send it?"))
        r.input.send(UserInput(.mouseMoved(x: 900, y: 900), at: r.clock))
        r.input.send(UserInput(.mouseDown, at: r.clock))
        r.model.answer(true)
        #expect(r.sent == [.confirmAnswer(id: "q1", yes: true)])
        #expect(r.model.question == nil && r.model.handsActive)
        r.input.send(UserInput(.key, at: r.clock))
        #expect(r.sent.count == 1, "still not watching until the brain says the question is over")
        r.brain.emit(.confirmDone(id: "q1", answer: "yes"))
        r.input.send(UserInput(.key, at: r.clock + 1))
        #expect(r.sent.last == .handsStop(reason: "user"), "watching again after the answer")
    }

    @Test func aSpokenAnswerDoesntStopTheSessionEither() {
        let r = Rig()
        r.startSession(borrowed: true)
        r.brain.emit(.confirm(id: "q1", question: "Send it?"))
        r.input.send(UserInput(.key, at: r.clock))  // the talk key, to say "yes"
        r.brain.emit(.confirmDone(id: "q0", answer: "no"))
        r.input.send(UserInput(.key, at: r.clock))
        #expect(r.model.question != nil && r.sent.isEmpty, "another question's end leaves this one waiting")
        r.brain.emit(.confirmDone(id: "q1", answer: "yes"))
        #expect(r.model.question == nil && r.model.handsActive)
        r.input.send(UserInput(.key, at: r.clock + 1))
        #expect(r.sent.last == .handsStop(reason: "user"))
    }

    // MARK: Background work

    @Test func inTheBackgroundTheUsersOwnWorkNeverStopsMilo() {
        let r = Rig()
        r.startSession()
        for input in [UserInput(.key, at: r.clock), UserInput(.mouseDown, at: r.clock), UserInput(.scroll, at: r.clock),
                      UserInput(.mouseMoved(x: 700, y: 700), at: r.clock + 1)] {
            r.input.send(input)
        }
        #expect(r.sent.isEmpty && r.model.handsActive)
        r.input.send(UserInput(.escape, at: r.clock + 2))
        #expect(r.sent == [.handsStop(reason: "escape")], "esc still stops him")
    }

    @Test func describeOutlinesTheWindowAndGlidesTheCursorBeforeTheClick() {
        let r = Rig()
        r.startSession()
        r.describesAButton()
        r.cursor.hold = true
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        #expect(r.model.workingWindow == CGRect(x: 100, y: 350, width: 800, height: 600), "AppKit: y flips")
        #expect(r.windows.watched.map(\.pid) == [42])
        #expect(r.cursor.calls == ["glide 600,600"])
        r.brain.emit(.handsRequest(id: "h2", tool: "click", args: ["x": 1, "y": 2]))
        #expect(r.hands.performed == ["describe"], "the click waits for the cursor to get there")
        r.cursor.land()
        #expect(r.hands.performed == ["describe", "click"])
        #expect(r.cursor.calls == ["glide 600,600", "click 600,600"])
    }

    @Test func theWindowComesForwardOnceWhenMiloStartsInItAndAgainForTheNextApp() {
        let r = Rig()
        r.startSession()
        r.describesAButton()
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        r.brain.emit(.handsRequest(id: "h2", tool: "describe", args: ["tool": "type", "text": "hi"]))
        r.brain.emit(.handsRequest(id: "h3", tool: "describe", args: ["tool": "scroll"]))
        #expect(r.windows.broughtForward == [42], "once, so a click away to keep working isn't undone")

        r.hands.results["describe"] = .success([
            "app": "Excel", "point": .object(["x": 10, "y": 10]), "pid": 7,
            "window": .object(["x": 0, "y": 0, "width": 500, "height": 400]),
        ])
        r.brain.emit(.handsRequest(id: "h4", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        #expect(r.windows.broughtForward == [42, 7])

        r.brain.emit(.handsSession(false))
        r.brain.emit(.handsSession(true))
        r.brain.emit(.handsRequest(id: "h5", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        #expect(r.windows.broughtForward == [42, 7, 7], "a new session starts fresh")
    }

    @Test func showAppBringsTheWindowOfTheAppAScriptWorksInForwardAndOutlinesIt() {
        let r = Rig()
        r.startSession()
        r.windows.mainWindows["Microsoft Excel"] = (pid: 9, frame: CGRect(x: 100, y: 50, width: 800, height: 600))
        r.brain.emit(.handsRequest(id: "s1", tool: "show_app", args: ["app": "Microsoft Excel", "bundle": ""]))
        #expect(r.windows.broughtForward == [9])
        #expect(r.windows.watched.map(\.pid) == [9])
        #expect(r.model.workingWindow == CGRect(x: 100, y: 350, width: 800, height: 600))
        #expect(r.sent == [.handsResult(id: "s1", ok: true, result: ["shown": true])])
        #expect(r.hands.performed.isEmpty, "the app shows it itself")
    }

    @Test func showAppForAnAppWithoutAWindowAnswersAndDoesNothing() {
        let r = Rig()
        r.startSession()
        r.brain.emit(.handsRequest(id: "s1", tool: "show_app", args: ["app": "Numbers", "bundle": ""]))
        #expect(r.windows.broughtForward.isEmpty && r.model.workingWindow == nil)
        #expect(r.sent == [.handsResult(id: "s1", ok: true, result: ["shown": false])])
    }

    @Test func withShowWindowOffShowAppOnlyOutlines() {
        let r = Rig()
        r.screen.showWindow = { false }
        r.startSession()
        r.windows.mainWindows["Microsoft Excel"] = (pid: 9, frame: CGRect(x: 100, y: 50, width: 800, height: 600))
        r.brain.emit(.handsRequest(id: "s1", tool: "show_app", args: ["app": "Microsoft Excel", "bundle": ""]))
        #expect(r.windows.broughtForward.isEmpty && r.model.workingWindow != nil)
    }

    @Test func withShowWindowOffMiloStaysBehindTheUsersWindows() {
        let r = Rig()
        r.screen.showWindow = { false }
        r.startSession()
        r.describesAButton()
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        #expect(r.windows.broughtForward.isEmpty)
        #expect(r.windows.watched.map(\.pid) == [42], "the outline still shows where he works")
    }

    @Test func aCursorThatNeverArrivesDoesntHoldTheActionForever() {
        let r = Rig()
        r.startSession()
        r.describesAButton()
        r.cursor.hold = true
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        r.brain.emit(.handsRequest(id: "h2", tool: "click", args: ["x": 1, "y": 2]))
        r.scheduler.advance(by: ScreenController.glideWait)
        #expect(r.hands.performed == ["describe", "click"])
    }

    @Test func typingShowsTheCaretHint() {
        let r = Rig()
        r.startSession()
        r.describesAButton()
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "type", "text": "hi"]))
        r.brain.emit(.handsRequest(id: "h2", tool: "type", args: ["text": "hi"]))
        #expect(r.cursor.calls.last == "typing 600,600")
    }

    @Test func theOutlineFollowsTheWindowAndGoesWhenItCloses() {
        let r = Rig()
        r.startSession()
        r.describesAButton()
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        r.windows.move(to: CGRect(x: 300, y: 50, width: 800, height: 600))
        #expect(r.model.workingWindow == CGRect(x: 300, y: 350, width: 800, height: 600))
        r.windows.move(to: nil)
        #expect(r.model.workingWindow == nil)
    }

    @Test func theOutlineHidesWhileTheWindowIsMinimizedAndComesBackWithIt() {
        let r = Rig()
        r.startSession()
        r.describesAButton()
        r.windows.windowNumber = 99  // the window watched before
        r.windows.nextNumber = 4711
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        #expect(r.model.workingWindowNumber == 4711, "so the outline can sit just above that window")
        r.windows.move(to: nil)
        #expect(r.model.workingWindow == nil && r.windows.stops == 0, "still watched while it is away")
        r.windows.move(to: CGRect(x: 100, y: 50, width: 800, height: 600))
        #expect(r.model.workingWindow == CGRect(x: 100, y: 350, width: 800, height: 600))
        r.brain.emit(.handsSession(false))
        #expect(r.model.workingWindowNumber == nil)
    }

    @Test func pipStaysOnTheWindowWhileTheBrainPointsAtSpotsInIt() {
        let r = Rig()
        r.startSession()
        r.brain.emit(.flyTo(ScreenPoint(x: 10, y: 10)))
        #expect(r.model.flyTarget == CGPoint(x: 10, y: 990), "no window known yet: he flies to the spot")
        r.describesAButton()
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        #expect(r.model.flyTarget == nil && r.model.workingWindow != nil)
        r.brain.emit(.flyTo(ScreenPoint(x: 600, y: 400)))
        #expect(r.model.flyTarget == nil, "he perches on the window instead")
    }

    @Test func theEndOfTheSessionClearsTheScreen() {
        let r = Rig()
        r.startSession(borrowed: true)
        r.describesAButton()
        r.brain.emit(.handsRequest(id: "h1", tool: "describe", args: ["tool": "click", "x": 1, "y": 2]))
        r.brain.emit(.handsSession(false))
        #expect(r.model.workingWindow == nil && !r.model.handsBorrowed && r.hands.borrowed.isEmpty)
        #expect(r.windows.stops >= 1 && r.cursor.calls.last == "rest")
    }

    @Test func aFailureThatNeedsTheMouseTellsTheBrain() {
        let r = Rig()
        r.startSession()
        r.hands.result = .failure(HandsFailure("Excel doesn't take clicks in the background.", borrow: "mouse"))
        r.brain.emit(.handsRequest(id: "h1", tool: "click", args: ["x": 1, "y": 2]))
        #expect(r.sent == [.handsResult(id: "h1", ok: false, result: ["borrow": "mouse"],
                                        error: "Excel doesn't take clicks in the background.")])
    }

    @Test func theMouseGoesBackAWhileAfterTheLastBorrowedAction() {
        let r = Rig()
        r.startSession()
        r.brain.emit(.handsBorrow(on: true, what: "mouse"))
        #expect(r.model.handsBorrowed && r.hands.borrowed == ["mouse"])
        r.scheduler.advance(by: ScreenController.lendFor - 1)
        r.brain.emit(.handsRequest(id: "h1", tool: "click", args: ["x": 1, "y": 2]))
        r.scheduler.advance(by: ScreenController.lendFor - 1)
        #expect(r.model.handsBorrowed, "each action starts the wait again")
        r.scheduler.advance(by: 1)
        #expect(!r.model.handsBorrowed && r.hands.borrowed.isEmpty)
        r.input.send(UserInput(.mouseDown, at: r.clock + 5))
        #expect(r.model.handsActive, "back in the background, touching the mouse is fine again")
    }

    @Test func theStopButtonStopsLikeEsc() {
        let r = Rig()
        r.startSession()
        r.screen.stopPressed()
        #expect(r.sent == [.handsStop(reason: "escape")] && !r.model.handsActive)
    }

    @Test func theStopByMiloStopsTheScreenWorkAndTellsTheBrainToStopEverything() {
        let r = Rig()
        r.startSession()
        r.model.stopAll()
        #expect(r.sent == [.handsStop(reason: "escape"), .stopAll] && !r.model.handsActive)
        r.brain.emit(.handsRequest(id: "h1", tool: "click", args: ["x": 1, "y": 2]))
        #expect(r.hands.performed.isEmpty, "nothing more runs on screen")
    }

    @Test func theStopByMiloOutsideScreenWorkOnlyTellsTheBrain() {
        let r = Rig()
        r.model.stopAll()
        #expect(r.sent == [.stopAll])
    }

    @Test func aBorrowOutsideASessionIsIgnored() {
        let r = Rig()
        r.brain.emit(.handsBorrow(on: true, what: "mouse"))
        #expect(!r.model.handsBorrowed && r.hands.borrowed.isEmpty)
    }

    @Test func lendingTheMouseDoesNotLendTheKeyboard() {
        let r = Rig()
        r.startSession()
        r.brain.emit(.handsBorrow(on: true, what: "mouse"))
        #expect(r.hands.borrowed == ["mouse"], "a yes for the mouse never lends the keyboard")
        r.brain.emit(.handsBorrow(on: true, what: "keyboard"))
        #expect(r.hands.borrowed == ["mouse", "keyboard"])
        r.brain.emit(.handsSession(false))
        #expect(r.hands.borrowed.isEmpty)
    }
}
