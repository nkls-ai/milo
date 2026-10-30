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
    let scheduler = ManualScheduler()
    let model: MiloModel
    let screen: ScreenController
    let controller: MiloController
    var clock: TimeInterval = 100

    init() {
        model = MiloModel(scheduler: scheduler)
        let ports = ScreenPorts(reader: reader, hands: hands, input: input, hotkey: hotkey)
        var now: () -> TimeInterval = { 0 }
        screen = ScreenController(model: model, brain: brain, ports: ports, now: { now() },
                                  toAppKit: { CGPoint(x: $0.x, y: 1000 - $0.y) })
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

    /// Starts a session with the pointer resting at (0, 0) a while ago.
    func startSession() {
        brain.emit(.handsSession(true))
        input.send(UserInput(.mouseMoved(x: 0, y: 0), at: clock))
        clock += 1
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

    @Test func realInputStopsTheSessionAtOnce() {
        let r = Rig()
        r.startSession()
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
        r.startSession()
        r.brain.emit(.handsRequest(id: "hands-1", tool: "click", args: ["x": 600, "y": 400]))
        r.input.send(UserInput(.mouseMoved(x: 600, y: 400), at: r.clock + 0.1))
        r.input.send(UserInput(.mouseDown, at: r.clock + 0.1, synthetic: true))
        #expect(r.sent == [.handsResult(id: "hands-1", ok: true, result: ["text": "done"])])
        #expect(r.model.handsActive)
    }

    @Test func afterAStopActionsAreRefusedUntilTheBrainEndsTheSession() {
        let r = Rig()
        r.startSession()
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
        r.startSession()
        r.brain.emit(.confirmRequest(id: "confirm-1", text: "Send it?"))
        #expect(r.model.question == MiloModel.Question(id: "confirm-1", text: "Send it?"))
        r.input.send(UserInput(.mouseMoved(x: 900, y: 900), at: r.clock))
        r.input.send(UserInput(.mouseDown, at: r.clock))
        r.controller.screen?.answer(yes: true)
        #expect(r.sent == [.confirmResult(id: "confirm-1", yes: true)])
        #expect(r.model.question == nil && r.model.handsActive)
        r.input.send(UserInput(.key, at: r.clock + 1))
        #expect(r.sent.last == .handsStop(reason: "user"), "watching again after the answer")
    }

    @Test func aTimedOutQuestionGoesAway() {
        let r = Rig()
        r.brain.emit(.confirmRequest(id: "confirm-1", text: "Send it?"))
        r.brain.emit(.confirmEnd(id: "confirm-0"))
        #expect(r.model.question != nil, "another question's end leaves this one")
        r.brain.emit(.confirmEnd(id: "confirm-1"))
        #expect(r.model.question == nil)
        r.controller.screen?.answer(yes: true)
        #expect(r.sent.isEmpty, "nothing to answer any more")
    }
}
