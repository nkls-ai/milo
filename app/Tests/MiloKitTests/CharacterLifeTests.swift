import CoreGraphics
import Foundation
import Testing
@testable import MiloKit

@Suite struct CharacterLifeTests {
    /// Runs `life` from its last update until `end`, stepping only at the times it asked to wake.
    private func run(_ life: inout CharacterLife, _ input: LifeInput, until end: TimeInterval) -> [(TimeInterval, LifePose)] {
        var poses: [(TimeInterval, LifePose)] = []
        while life.wake <= end {
            let now = life.wake
            poses.append((now, life.update(input, at: now)))
        }
        return poses
    }

    @Test func sameSeedGivesTheSameDay() {
        var a = CharacterLife(seed: 7)
        var b = CharacterLife(seed: 7)
        _ = a.update(LifeInput(), at: 0)
        _ = b.update(LifeInput(), at: 0)
        let first = run(&a, LifeInput(), until: 120)
        let second = run(&b, LifeInput(), until: 120)
        #expect(first.map(\.0) == second.map(\.0))
        #expect(first.map(\.1) == second.map(\.1))
    }

    @Test func idleWakesRarelyButBlinksAndGlances() {
        var life = CharacterLife(seed: 1)
        _ = life.update(LifeInput(), at: 0)
        let poses = run(&life, LifeInput(), until: 600)
        // Under one wake a second (mostly a blink's start and end). Each is one pose update,
        // and the view redraws only when the pose differs.
        #expect(poses.count < 600)
        #expect(zip(poses, poses.dropFirst()).allSatisfy { $0.1.0 > $0.0.0 })
        #expect(poses.contains { $0.1.blink })
        #expect(poses.contains { $0.1.gaze != .zero })
        #expect(poses.contains { $0.1.squash > 0 || $0.1.tilt != 0 })
    }

    @Test func eyesFollowAMovingCursorThenLoseInterest() {
        var life = CharacterLife(seed: 2)
        var input = LifeInput(cursor: CGPoint(x: 400, y: 10))
        _ = life.update(input, at: 0)
        input.cursor = CGPoint(x: 400, y: 0)
        let pose = life.update(input, at: 0.5)
        #expect(pose.gaze == CGVector(dx: 1, dy: 0))
        input.cursor = CGPoint(x: -300, y: 300)
        #expect(life.update(input, at: 0.6).gaze == CGVector(dx: -0.7, dy: -0.7))
        #expect(life.wake <= 0.6 + CharacterLife.attention)
        #expect(life.update(input, at: 0.6 + CharacterLife.attention).gaze == .zero)
    }

    @Test func hoverSmilesAndHopsThenSettles() {
        var life = CharacterLife(seed: 3)
        var input = LifeInput(cursor: CGPoint(x: 300, y: 0))
        _ = life.update(input, at: 0)
        input.cursor = CGPoint(x: 10, y: 20)
        let first = life.update(input, at: 1)
        #expect(first.hovered && first.pleased)
        #expect(first.squash < 0)
        #expect(life.update(input, at: 1.15).squash > 0)
        let later = life.update(input, at: 2.3)
        #expect(later.hovered && !later.pleased)
        #expect(later.squash == 0)
    }

    @Test func hoverOpensASleepingMilosEyesWithoutASmile() {
        var life = CharacterLife(seed: 4)
        var input = LifeInput(asleep: true, cursor: CGPoint(x: 300, y: 0))
        _ = life.update(input, at: 0)
        input.cursor = .zero
        let pose = life.update(input, at: 1)
        #expect(pose.hovered && !pose.pleased)
    }

    @Test func leansTowardTheMiddleOfTheScreenWhileListening() {
        var life = CharacterLife(seed: 5)
        _ = life.update(LifeInput(), at: 0)
        let left = life.update(LifeInput(state: .listening, towardCentre: -1), at: 1)
        #expect(left.lean == -1)
        #expect(abs(left.gaze.dx) < 0.3 && abs(left.gaze.dy) < 0.3)
        let right = life.update(LifeInput(state: .listening, towardCentre: 1), at: 1.5)
        #expect(right.lean == 1)
        #expect(life.update(LifeInput(), at: 2).lean == 0)
    }

    @Test func stateChangesSquashThenSpringBack() {
        var life = CharacterLife(seed: 6)
        _ = life.update(LifeInput(), at: 0)
        let input = LifeInput(state: .listening)
        #expect(life.update(input, at: 1).squash < 0)
        #expect(life.update(input, at: 1.1).squash > 0)
        #expect(life.update(input, at: 1.3).squash == 0)
    }

    @Test func speakingLooksAtTheBubbleFirstThenBackAtTheUser() {
        var life = CharacterLife(seed: 8)
        _ = life.update(LifeInput(), at: 0)
        let input = LifeInput(state: .speaking)
        #expect(life.update(input, at: 1).gaze.dy < -0.5)
        let gazes = run(&life, input, until: 15).map(\.1.gaze)
        #expect(gazes.contains(.zero))
        #expect(gazes.contains { $0.dy < -0.5 })
    }

    @Test func thinkingLooksUpAndSearchesSideToSide() {
        var life = CharacterLife(seed: 9)
        _ = life.update(LifeInput(), at: 0)
        let input = LifeInput(state: .thinking)
        _ = life.update(input, at: 1)
        let gazes = run(&life, input, until: 10).map(\.1.gaze)
        #expect(gazes.allSatisfy { $0.dy < 0 })
        #expect(gazes.contains { $0.dx > 0 } && gazes.contains { $0.dx < 0 })
    }

    @Test func fallingAsleepYawnsOnceThenStaysStill() {
        var life = CharacterLife(seed: 10)
        _ = life.update(LifeInput(), at: 0)
        let input = LifeInput(asleep: true)
        _ = life.update(input, at: 1)
        let poses = run(&life, input, until: 3600)
        #expect(poses.contains { $0.1.yawn })
        #expect(!poses.contains { $0.1.blink })
        #expect(poses.allSatisfy { $0.0 < 4 })
        #expect(life.wake == .infinity)
    }

    @Test func yawnsMoreWhenItsLate() {
        func yawns(late: Bool) -> Int {
            var life = CharacterLife(seed: 11)
            let input = LifeInput(late: late)
            _ = life.update(input, at: 0)
            let poses = run(&life, input, until: 1800)
            return zip(poses, poses.dropFirst()).filter { !$0.0.1.yawn && $0.1.1.yawn }.count
        }
        #expect(yawns(late: true) > yawns(late: false) + 5)
    }

    @Test func aCursorSweepingFarAwayTurnsTheEyesOnlyAFewTimes() {
        // Across a whole 1400 pt wide screen, 300 pt above Milo, in 10 pt steps.
        let gazes = stride(from: -1400.0, through: 0, by: 10).map { CharacterLife.gaze(toward: CGPoint(x: $0, y: 300)) }
        let turns = zip(gazes, gazes.dropFirst()).filter { $0 != $1 }.count
        #expect(turns <= 4)
    }

    @Test func gazeReachesTheEdgeOnlyForFarCursors() {
        #expect(CharacterLife.gaze(toward: CGPoint(x: 0, y: 80)) == CGVector(dx: 0, dy: -0.5))
        #expect(CharacterLife.gaze(toward: CGPoint(x: 0, y: -900)) == CGVector(dx: 0, dy: 1))
        #expect(CharacterLife.gaze(toward: .zero) == .zero)
    }
}

@Suite struct CharacterLifeDriverTests {
    let scheduler = ManualScheduler()
    let driver: CharacterLifeDriver

    init() {
        let scheduler = scheduler
        driver = CharacterLifeDriver(scheduler: scheduler, clock: { Date(timeIntervalSinceReferenceDate: 12 * 3600 + scheduler.now) }, seed: 1)
    }

    @Test func pollsFastOnScreenSlowWhenHiddenAndStopsCleanly() {
        var reads = 0
        var visible = true
        driver.sense = {
            reads += 1
            return visible ? LifeSenses(cursor: CGPoint(x: 500, y: 0), towardCentre: -1) : nil
        }
        driver.start()
        scheduler.advance(by: 1)
        #expect(reads >= 10 && reads <= 12)
        visible = false
        scheduler.advance(by: 0.1)
        #expect(!driver.onScreen)
        reads = 0
        scheduler.advance(by: 5)
        #expect(reads == 5)
        driver.stop()
        #expect(scheduler.pendingCount == 0)
    }

    @Test func publishesOnlyWhenThePoseChanges() {
        var cursor = CGPoint(x: 500, y: 0)
        driver.sense = { LifeSenses(cursor: cursor, towardCentre: -1) }
        var published = 0
        let watch = driver.objectWillChange.sink { published += 1 }
        driver.start()
        scheduler.advance(by: 0.05)
        published = 0
        cursor = CGPoint(x: 500, y: 30)
        scheduler.advance(by: 0.2)
        cursor = CGPoint(x: 501, y: 30)
        scheduler.advance(by: 0.2)
        // Two polls a cursor barely moving: the gaze rounds to the same tenths, so at most a blink redraws.
        #expect(published <= 2)
        driver.update(state: .listening, asleep: false)
        #expect(driver.pose.lean == -1)
        watch.cancel()
        driver.stop()
    }
}
