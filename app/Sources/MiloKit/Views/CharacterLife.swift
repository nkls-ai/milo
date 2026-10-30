import CoreGraphics
import Foundation

/// What the life layer knows about the world at one moment.
struct LifeInput: Equatable {
    var state: MiloState = .idle
    /// Drowsy, idle and quiet: eyes closed.
    var asleep = false
    /// Late at night: he yawns now and then even when awake.
    var late = false
    /// Cursor position relative to Milo's centre in points, y up (AppKit). Nil when unknown or hidden.
    var cursor: CGPoint?
    /// -1 when the middle of the screen (where the user sits) is to Milo's left, 1 when it's to his right.
    var towardCentre: Double = -1
}

/// How the body should look right now. The view animates between poses, so a pose only changes at discrete moments.
struct LifePose: Equatable {
    /// Where the eyes look, each axis -1...1, x right, y down. Zero looks out at the user.
    var gaze = CGVector.zero
    /// -1...1, leaning toward the user. Negative leans left.
    var lean = 0.0
    /// Positive stretches taller, negative squashes flatter.
    var squash = 0.0
    /// Extra tilt in degrees, positive is clockwise.
    var tilt = 0.0
    var blink = false
    var yawn = false
    /// The cursor is over him.
    var hovered = false
    /// A short smile when the cursor first arrives.
    var pleased = false
    /// A small idle habit playing now; the figure performs it.
    var habit: Habit?
    /// -1 when the middle of the screen is to his left, 1 to his right: the way he faces.
    var side = -1.0

    /// Little things a wren does when nothing is going on, each a second or less.
    enum Habit: Equatable {
        /// The tail flicks up and settles.
        case tailFlick
        /// The quick knee-dip wrens do.
        case bob
        /// A wing tugs the scarf straight.
        case scarfTug
        /// A shake that puffs and smooths his feathers.
        case ruffle
        /// One wing stretched out and folded again.
        case wingStretch
    }
}

/// Decides Milo's idle life: gaze, blinks, glances, stretches, yawns, fidgets and squash on state changes.
/// Pure: time comes in through `update(_:at:)` and randomness from a seed, so tests can replay a day.
struct CharacterLife {
    /// The body in the same coordinates as `LifeInput.cursor`.
    static let body = CGRect(x: -54, y: -50, width: 108, height: 112)
    /// How long the eyes keep following a cursor that stopped moving.
    static let attention: TimeInterval = 2.5

    private enum Action: Equatable {
        case glance(CGVector), stretch, yawn, fidget, habit(LifePose.Habit)

        var duration: TimeInterval {
            switch self {
            case .glance: 1.2
            case .stretch: 1.3
            case .yawn: 1.9
            case .fidget: 0.6
            case let .habit(habit): habit == .wingStretch || habit == .scarfTug ? 1.2 : 0.6
            }
        }

        /// Offsets from the start where the pose changes.
        var marks: [TimeInterval] {
            switch self {
            case .glance: []
            case .stretch: [0.6]
            case .yawn: [0.25, 1.5]
            case .fidget: [0.15, 0.3, 0.45]
            case .habit: []
            }
        }
    }

    private var rng: SeededRandom
    private var last = LifeInput()
    private var started = false

    private var nextBlink: TimeInterval
    private var blinkEnd: TimeInterval = 0
    private var secondBlink: TimeInterval?

    private var bounce: [(squash: Double, until: TimeInterval)] = []
    private var pleasedUntil: TimeInterval = 0
    private var hovered = false

    private var lastCursor: CGPoint?
    private var cursorMovedAt: TimeInterval = -.infinity

    private var action: Action?
    private var actionStart: TimeInterval = 0
    private var nextAction: TimeInterval

    /// Speaking: alternates between the bubble and the user. Thinking: between left and right.
    private var lookAway = true
    private var lookSwitch: TimeInterval = 0

    /// When the pose next changes without new input. `.infinity` while nothing is scheduled.
    private(set) var wake: TimeInterval = .infinity

    init(seed: UInt64, at now: TimeInterval = 0) {
        rng = SeededRandom(seed: seed)
        nextBlink = now + 3
        nextAction = now + 4
    }

    mutating func update(_ input: LifeInput, at now: TimeInterval) -> LifePose {
        react(to: input, at: now)
        advance(input, at: now)
        last = input
        started = true
        let pose = pose(for: input, at: now)
        wake = nextWake(input, after: now)
        return pose
    }

    // MARK: Events

    private mutating func react(to input: LifeInput, at now: TimeInterval) {
        if started && input.state != last.state {
            bounce = Self.bounce(from: last.state, to: input.state, at: now)
            action = nil
            nextAction = now + rng.next(in: 2...5)
            lookSwitch = now
            lookAway = false
            blink(at: now)
        }
        if started && input.asleep != last.asleep {
            if input.asleep {
                start(.yawn, at: now)
            } else {
                action = nil
                bounce = [(0.07, now + 0.18)]
                nextAction = now + rng.next(in: 3...6)
            }
        }

        let over = input.cursor.map { Self.body.contains($0) } ?? false
        if over && !hovered {
            bounce = [(-0.09, now + 0.1), (0.07, now + 0.26)]
            if !input.asleep { pleasedUntil = now + 1.2 }
            if case .glance = action { action = nil }
        }
        hovered = over

        if let cursor = input.cursor {
            if let previous = lastCursor, hypot(cursor.x - previous.x, cursor.y - previous.y) > 4 {
                cursorMovedAt = now
            }
            lastCursor = cursor
        } else {
            lastCursor = nil
        }
    }

    private mutating func advance(_ input: LifeInput, at now: TimeInterval) {
        bounce.removeAll { $0.until <= now }

        if input.asleep {
            blinkEnd = 0
            secondBlink = nil
        } else if let second = secondBlink, now >= second {
            secondBlink = nil
            blinkEnd = now + 0.12
        } else if now >= nextBlink {
            blink(at: now)
            if rng.chance(0.15) { secondBlink = now + 0.3 }
        }

        if let action, now >= actionStart + action.duration {
            self.action = nil
            nextAction = now + rng.next(in: 5...12)
        }
        guard action == nil, input.state == .idle, !input.asleep, now >= nextAction else { return }
        if hovered || following(at: now) {
            nextAction = now + rng.next(in: 1...2.5)
            return
        }
        start(pickAction(late: input.late), at: now)
    }

    private mutating func blink(at now: TimeInterval) {
        blinkEnd = now + 0.12
        nextBlink = now + rng.next(in: 2.5...6)
    }

    private mutating func start(_ new: Action, at now: TimeInterval) {
        action = new
        actionStart = now
    }

    private mutating func pickAction(late: Bool) -> Action {
        let roll = rng.next(in: 0...1)
        let yawn = late ? 0.25 : 0.03
        if roll < yawn { return .yawn }
        if roll < yawn + 0.08 { return .stretch }
        if roll < yawn + 0.14 { return .fidget }
        if roll < yawn + 0.24 { return .habit(.bob) }
        if roll < yawn + 0.32 { return .habit(.tailFlick) }
        if roll < yawn + 0.37 { return .habit(.scarfTug) }
        if roll < yawn + 0.42 { return .habit(.ruffle) }
        if roll < yawn + 0.47 { return .habit(.wingStretch) }
        let angle = rng.next(in: 0...(2 * .pi))
        let reach = rng.next(in: 0.5...1)
        return .glance(Self.quantized(CGVector(dx: cos(angle) * reach, dy: sin(angle) * reach * 0.6)))
    }

    private static func bounce(from old: MiloState, to new: MiloState, at now: TimeInterval) -> [(squash: Double, until: TimeInterval)] {
        switch new {
        case .listening, .dictating: [(-0.06, now + 0.08), (0.08, now + 0.24)]
        case .speaking: [(0.05, now + 0.16)]
        case .thinking, .transcribing: [(-0.05, now + 0.16)]
        case .idle: old == .idle ? [] : [(-0.07, now + 0.2)]
        }
    }

    private func following(at now: TimeInterval) -> Bool {
        lastCursor != nil && now - cursorMovedAt < Self.attention
    }

    // MARK: Pose

    private mutating func pose(for input: LifeInput, at now: TimeInterval) -> LifePose {
        var pose = LifePose()
        pose.hovered = hovered
        pose.pleased = hovered && now < pleasedUntil
        pose.blink = now < blinkEnd
        pose.squash = bounce.first?.squash ?? 0
        let side = input.towardCentre
        pose.side = side

        switch input.state {
        case .listening:
            pose.gaze = CGVector(dx: 0.15 * side, dy: -0.1)
            pose.lean = side
            pose.tilt = 4 * side
        case .thinking, .transcribing:
            if now >= lookSwitch {
                lookAway.toggle()
                lookSwitch = now + rng.next(in: 1.2...2.6)
            }
            pose.gaze = CGVector(dx: lookAway ? 0.7 : -0.7, dy: -0.75)
        case .speaking:
            if now >= lookSwitch {
                lookAway.toggle()
                lookSwitch = now + (lookAway ? rng.next(in: 1.6...3) : rng.next(in: 0.8...1.6))
            }
            pose.gaze = lookAway ? CGVector(dx: 0.3 * side, dy: -0.8) : .zero
        case .dictating, .idle:
            if hovered || following(at: now), let cursor = input.cursor {
                pose.gaze = Self.gaze(toward: cursor)
            }
        }

        if input.asleep {
            pose.gaze = .zero
            pose.blink = false
        }
        if let action {
            let t = now - actionStart
            switch action {
            case let .glance(direction):
                pose.gaze = direction
            case .stretch:
                if t < 0.6, pose.squash == 0 { pose.squash = 0.08 }
            case .yawn:
                pose.yawn = t >= 0.25 && t < 1.5
                if pose.yawn {
                    pose.tilt = -5 * side
                    if pose.squash == 0 { pose.squash = 0.04 }
                }
            case .fidget:
                pose.tilt = [6, -5, 3, 0][min(3, Int(t / 0.15))]
            case let .habit(habit):
                pose.habit = habit
            }
        }
        return pose
    }

    /// Eyes point toward the cursor and reach the edge of the eye once it's 160 pt away. The direction comes in
    /// 16 steps and the reach in quarters, so a cursor moving about the screen turns his eyes a few times,
    /// not on every poll: each turn redraws him.
    static func gaze(toward cursor: CGPoint) -> CGVector {
        let distance = hypot(cursor.x, cursor.y)
        guard distance > 1 else { return .zero }
        let reach = max(0.25, (min(1, distance / 160) * 4).rounded() / 4)
        let step = Double.pi / 8
        let angle = (atan2(-cursor.y, cursor.x) / step).rounded() * step
        return quantized(CGVector(dx: cos(angle) * reach, dy: sin(angle) * reach))
    }

    /// Tenths, so small cursor moves don't redraw the face.
    private static func quantized(_ v: CGVector) -> CGVector {
        CGVector(dx: (v.dx * 10).rounded() / 10, dy: (v.dy * 10).rounded() / 10)
    }

    private func nextWake(_ input: LifeInput, after now: TimeInterval) -> TimeInterval {
        var times: [TimeInterval] = bounce.map(\.until)
        if !input.asleep {
            times.append(nextBlink)
            if blinkEnd > now { times.append(blinkEnd) }
            if let secondBlink { times.append(secondBlink) }
        }
        if pleasedUntil > now { times.append(pleasedUntil) }
        if lastCursor != nil, cursorMovedAt + Self.attention > now { times.append(cursorMovedAt + Self.attention) }
        if let action {
            times += action.marks.map { actionStart + $0 }
            times.append(actionStart + action.duration)
        } else if input.state == .idle && !input.asleep {
            times.append(nextAction)
        }
        if input.state == .speaking || input.state == .thinking || input.state == .transcribing {
            times.append(lookSwitch)
        }
        return times.filter { $0 > now }.min() ?? .infinity
    }
}

/// SplitMix64: small, fast and the same sequence for the same seed on every run.
struct SeededRandom: RandomNumberGenerator {
    private var state: UInt64

    init(seed: UInt64) { state = seed }

    mutating func next() -> UInt64 {
        state &+= 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    mutating func next(in range: ClosedRange<Double>) -> Double { Double.random(in: range, using: &self) }
    mutating func chance(_ p: Double) -> Bool { next(in: 0...1) < p }
}
