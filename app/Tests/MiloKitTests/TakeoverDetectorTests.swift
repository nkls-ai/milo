import Testing
@testable import MiloKit

@Suite struct TakeoverDetectorTests {
    private func armed() -> TakeoverDetector {
        var d = TakeoverDetector(grace: 0.3, slop: 6)
        d.arm()
        return d
    }

    @Test func nothingCountsWhileDisarmed() {
        var d = TakeoverDetector()
        #expect(d.handle(UserInput(.escape, at: 1)) == nil)
        #expect(d.handle(UserInput(.key, at: 1)) == nil)
    }

    @Test func escAlwaysStops() {
        var d = armed()
        d.miloActs(at: 10)
        #expect(d.handle(UserInput(.escape, at: 10.05)) == .escape)
    }

    @Test func keysClicksAndScrollsStopAtOnce() {
        for kind in [UserInput.Kind.key, .mouseDown, .scroll] {
            var d = armed()
            #expect(d.handle(UserInput(kind, at: 5)) == .user)
        }
    }

    @Test func milosOwnMarkedEventsNeverCount() {
        var d = armed()
        #expect(d.handle(UserInput(.key, at: 1, synthetic: true)) == nil)
        #expect(d.handle(UserInput(.mouseDown, at: 1, synthetic: true)) == nil)
        #expect(d.handle(UserInput(.escape, at: 1, synthetic: true)) == nil)
        #expect(d.handle(UserInput(.mouseMoved(x: 500, y: 500), at: 1, synthetic: true)) == nil)
    }

    @Test func aRestingHandsJitterIsNotATakeover() {
        var d = armed()
        #expect(d.handle(UserInput(.mouseMoved(x: 100, y: 100), at: 1)) == nil, "the first move sets where it rests")
        #expect(d.handle(UserInput(.mouseMoved(x: 103, y: 102), at: 1.1)) == nil)
        #expect(d.handle(UserInput(.mouseMoved(x: 110, y: 100), at: 1.2)) == .user)
    }

    @Test func pointerMovesRightAfterMilosClickAreHis() {
        var d = armed()
        d.handle(UserInput(.mouseMoved(x: 0, y: 0), at: 1))
        d.miloActs(at: 2)
        #expect(d.handle(UserInput(.mouseMoved(x: 640, y: 412), at: 2.1)) == nil, "the warp to the click point")
        #expect(d.handle(UserInput(.mouseMoved(x: 641, y: 412), at: 2.4)) == nil, "rests where Milo left it")
        #expect(d.handle(UserInput(.mouseMoved(x: 700, y: 412), at: 2.5)) == .user, "after the grace it's the user")
    }

    @Test func graceDoesNotCoverKeys() {
        var d = armed()
        d.miloActs(at: 2)
        #expect(d.handle(UserInput(.key, at: 2.05)) == .user)
    }

    @Test func rearmingForgetsWhereThePointerRested() {
        var d = armed()
        d.handle(UserInput(.mouseMoved(x: 0, y: 0), at: 1))
        d.disarm()
        d.arm()
        #expect(d.handle(UserInput(.mouseMoved(x: 300, y: 300), at: 5)) == nil)
    }
}

@Suite struct TakeoverModeTests {
    @Test func inTheBackgroundOnlyEscStops() {
        var d = TakeoverDetector(mode: .background)
        d.arm()
        for input in [UserInput(.key, at: 1), UserInput(.mouseDown, at: 1), UserInput(.scroll, at: 1),
                      UserInput(.mouseMoved(x: 0, y: 0), at: 1), UserInput(.mouseMoved(x: 500, y: 500), at: 2)] {
            #expect(d.handle(input) == nil, "the user's own work never stops Milo in the background")
        }
        #expect(d.handle(UserInput(.escape, at: 3)) == .escape)
    }

    @Test func borrowingBringsBackTheStrictRules() {
        var d = TakeoverDetector(mode: .background)
        d.arm()
        _ = d.handle(UserInput(.mouseMoved(x: 0, y: 0), at: 1))
        d.mode = .borrowed
        #expect(d.handle(UserInput(.mouseMoved(x: 300, y: 0), at: 2)) == nil, "the switch is not a move")
        #expect(d.handle(UserInput(.mouseMoved(x: 320, y: 0), at: 3)) == .user)
        d.mode = .background
        #expect(d.handle(UserInput(.key, at: 4)) == nil)
    }

    @Test func withOnlyTheKeyboardLentMovingTheMouseIsNoTakeover() {
        var d = TakeoverDetector(grace: 0.3, slop: 6)
        d.arm()
        d.pointerCounts = false
        #expect(d.handle(UserInput(.mouseMoved(x: 0, y: 0), at: 1)) == nil)
        #expect(d.handle(UserInput(.mouseMoved(x: 600, y: 300), at: 1.2)) == nil)
        #expect(d.handle(UserInput(.key, at: 1.3)) == .user, "typing still takes the Mac back")
    }

    @Test func theWayBackFromTheYesButtonIsNoTakeover() {
        // The user, 2026-11-01: clicking OK on Milo's question "registered as me taking over".
        var d = TakeoverDetector(grace: 0.3, slop: 6)
        d.answered(at: 10)
        #expect(d.handle(UserInput(.mouseMoved(x: 900, y: 80), at: 10.1)) == nil)
        #expect(d.handle(UserInput(.mouseMoved(x: 500, y: 400), at: 11.2)) == nil)
        #expect(d.handle(UserInput(.mouseMoved(x: 300, y: 400), at: 12)) == .user, "later, with the mouse lent, it counts")
    }
}
