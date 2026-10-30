import CoreGraphics
import Foundation

/// Decides Milo's performance: from what the app tells the figure, the pose he holds and the moves he
/// makes on the way in and while he holds it. Pure: time comes in with each call, randomness from a seed.
struct WrenDirector {
    private var last: FigureInput?
    private var rng: SeededRandom
    /// The next beat of a state's own rhythm: a gesture while speaking, a tap while thinking.
    private var beat: Double = .infinity
    private var lastNod = -Double.infinity
    private var beats = 0

    /// When the director next wants to act without new input.
    var wake: Double { beat }

    /// A nod at most this often, so a fast talker doesn't make him bob like a toy.
    static let nodGap = 0.7

    init(seed: UInt64 = 1) {
        rng = SeededRandom(seed: seed)
    }

    /// Sets the motion's target for `input` and starts the moves its changes call for.
    mutating func direct(_ input: FigureInput, small: Bool = false, motion: inout WrenMotion, at now: Double,
                         reduceMotion: Bool = false) {
        motion.target = Self.pose(for: input, small: small)
        let before = last
        last = input
        guard let before else { return }
        if input.pose.blink && !before.pose.blink { motion.blink() }
        guard !reduceMotion else { beat = .infinity; return }
        for clip in Self.cues(from: before, to: input, side: input.pose.side) { motion.play(clip) }

        let speaking = input.state == .speaking
        let thinking = input.state == .thinking || input.state == .transcribing
        if input.words > before.words, input.state == .listening || input.state == .dictating, now - lastNod > Self.nodGap {
            lastNod = now
            motion.play(WrenClips.nod)
        }
        let rhythm = speaking || thinking || input.asking
        let wasRhythm = before.state == input.state && before.asking == input.asking
        if !rhythm {
            beat = .infinity
        } else if !wasRhythm || beat == .infinity {
            beats = 0
            beat = now + (speaking ? rng.next(in: 1.2...2.2) : input.asking ? 2.8 : rng.next(in: 0.9...1.5))
        }
        if now >= beat {
            beats += 1
            let near = input.pose.side
            if input.asking {
                motion.play(WrenClips.tailTick)
                beat = now + rng.next(in: 3.2...4.6)
            } else if speaking {
                motion.play(rng.chance(0.5) ? WrenClips.gesture(near: near) : WrenClips.emphasis)
                beat = now + rng.next(in: 2.2...4)
            } else {
                motion.play(beats % 4 == 0 ? WrenClips.bob : WrenClips.tap)
                beat = now + rng.next(in: 1.1...1.6)
            }
        }
    }

    // MARK: Poses

    /// The pose Milo holds for `input`. Everything here is a destination; springs get him there.
    static func pose(for input: FigureInput, small: Bool = false) -> WrenPose {
        var p = WrenPose.rest
        let life = input.pose
        let s = life.side
        let emotion = input.shown
        let sleeping = emotion == .sleepy && !life.yawn
        let level = min(1, max(0, input.level))

        p.turn = 0.2 * s
        p.gazeX = life.gaze.dx
        p.gazeY = life.gaze.dy
        p.headTilt = life.tilt
        p.squash = life.squash * 1.3
        p.lift = max(0, life.squash) * 60

        switch input.state {
        case .idle:
            break
        case .listening:
            p.lean = 4 * s
            p.lidL = 0.06; p.lidR = 0.06
            p.eyeL = 1.06; p.eyeR = 1.06
            p.browL = 0.35; p.browR = 0.35
            p.tail = 10 + level * 20
            p.tailFan = level
            p.squash += 0.02
        case .dictating:
            p.lean = 2.5 * s
            p.lidL = 0.14; p.lidR = 0.14
            p.browL = 0.15; p.browR = 0.15
            p.browTiltL = -0.1; p.browTiltR = -0.1
            p.tail = 6 + level * 16
            p.tailFan = level * 0.8
            p.gazeY += 0.2
        case .thinking, .transcribing:
            p.lidL = 0.28; p.lidR = 0.24
            // one brow up, the other down a touch: "hm"
            if s < 0 { p.browL = 0.75; p.browR = -0.1; p.browTiltR = -0.3 } else { p.browR = 0.75; p.browL = -0.1; p.browTiltL = -0.3 }
            p.headTilt += -6 * s
            p.tail = 4
        case .speaking:
            p.beak = pow(min(1, level * 1.25), 0.8)
            p.browL = 0.15 + level * 0.35; p.browR = p.browL
            p.headY = -level * 1.6
            p.lidL = 0.14; p.lidR = 0.14
            p.squash -= level * 0.025
            p.tail = 6
        }

        if input.working {
            p.lidL = 0.3; p.lidR = 0.3
            p.browL = -0.15; p.browR = -0.15
            p.browTiltL = -0.25; p.browTiltR = -0.25
            p.scarfToss = 1
            p.tail = max(p.tail, 4)
        }
        if input.asking {
            p.headTilt += 9 * s
            p.lidL = 0.05; p.lidR = 0.05
            p.eyeL = 1.08; p.eyeR = 1.08
            p.browL = 0.45; p.browR = 0.45
            p.browTiltL = 0.2; p.browTiltR = 0.2
            p.tail = 16
            p.tailFan = 0.4
        }

        switch emotion {
        case .neutral:
            break
        case .happy:
            p.lowerL = 1; p.lowerR = 1
            p.lidL = 0.2; p.lidR = 0.2
            p.blush = 0.55
            p.tail += 12
            p.browL = 0.35; p.browR = 0.35
            p.squash += 0.02
        case .excited:
            p.lowerL = 0.35; p.lowerR = 0.35
            p.lidL = 0; p.lidR = 0
            p.eyeL = 1.12; p.eyeR = 1.12
            p.beak = max(p.beak, 0.3)
            p.blush = 0.5
            p.tail += 20
            p.tailFan = max(p.tailFan, 0.7)
            p.browL = 0.6; p.browR = 0.6
            p.wingL = 12; p.wingR = 12
        case .thinking:
            if input.state != .thinking && input.state != .transcribing {
                p.lidL = 0.28; p.lidR = 0.24
                if s < 0 { p.browL = 0.75; p.browR = -0.1 } else { p.browR = 0.75; p.browL = -0.1 }
            }
        case .concerned:
            p.browTiltL = 1; p.browTiltR = 1
            p.browL = 0.1; p.browR = 0.1
            p.lidL = 0.3; p.lidR = 0.3
            p.tail -= 8
            p.wingL = -4; p.wingR = -4
            p.lean -= 2 * s
            p.squash -= 0.02
            p.headTilt -= 3 * s
        case .sad:
            p.lidL = 0.45; p.lidR = 0.45
            p.browTiltL = 0.8; p.browTiltR = 0.8
            p.browL = -0.2; p.browR = -0.2
            p.tail -= 16
            p.squash -= 0.04
            p.headY += 3
            p.gazeY = max(p.gazeY, 0.45)
            p.wingL = -4; p.wingR = -4
        case .confused:
            p.headTilt += -10 * s
            if s < 0 { p.browR = 0.7; p.browL = -0.25; p.browTiltL = -0.3 } else { p.browL = 0.7; p.browR = -0.25; p.browTiltR = -0.3 }
            p.lidL = s < 0 ? 0.3 : 0.12; p.lidR = s < 0 ? 0.12 : 0.3
            p.gazeX -= 0.3 * s
        case .sleepy:
            if sleeping {
                p.lidL = 1; p.lidR = 1
                p.lowerL = 0; p.lowerR = 0
                p.scarfUp = 1
                p.headY = 2.5
                p.headTilt = 5 * s
                p.squash = -0.06
                p.tail = -12
                p.gazeX = 0; p.gazeY = 0
                p.browL = -0.1; p.browR = -0.1
                p.wingL = -3; p.wingR = -3
            } else {
                p.lidL = 0.45; p.lidR = 0.45
            }
        }

        if life.yawn {
            p.beak = 1
            p.lidL = 0.8; p.lidR = 0.8
            p.lowerL = 0.35; p.lowerR = 0.35
            p.headTilt = -6 * s
            p.headY = -3
            p.squash = 0.05
            p.wingL = 16; p.wingR = 16
            p.browL = 0.3; p.browR = 0.3
        }

        switch input.flight {
        case .perched:
            break
        case let .flying(heading):
            p.fly = 1
            if abs(heading.dx) > 0.15 { p.turn = heading.dx > 0 ? 0.3 : -0.3 }
            p.lean = heading.dx * 12
            p.headTilt = heading.dx * 6
            p.gazeX = heading.dx * 0.7
            p.gazeY = heading.dy * 0.4
            p.feet = 0
            p.wingL = 40; p.wingR = 40
            p.lidL = 0.08; p.lidR = 0.08
            p.browL = 0.3; p.browR = 0.3
            p.tail = 0; p.tailFan = 1
            p.lift = 0; p.squash = 0
        case let .pointing(toward):
            p.turn = toward.dx < 0 ? -0.2 : 0.2
            p.gazeX = toward.dx * 0.85
            p.gazeY = toward.dy * 0.85
            p.headX = toward.dx * 2
            p.headY = toward.dy * 2
            p.lean = toward.dx * 4
            if !input.working {
                // the wing on that side spread and held toward the spot, like a hand
                let r = toward.dx < 0 ? atan2(-toward.dy, -toward.dx) : -atan2(toward.dy, toward.dx)
                let angle = min(70, max(-50, r * 180 / .pi))
                if toward.dx < 0 { p.wingL = angle; p.openL = 1 } else { p.wingR = angle; p.openR = 1 }
                p.browL = max(p.browL, 0.3); p.browR = max(p.browR, 0.3)
            }
        }
        return p
    }

    // MARK: Moves

    /// The moves a change of input calls for.
    static func cues(from a: FigureInput, to b: FigureInput, side s: Double) -> [WrenClip] {
        var clips: [WrenClip] = []
        let glad: Set<Emotion> = [.happy, .excited]
        let ea = a.shown, eb = b.shown

        // flight first: it overrides the rest
        switch (a.flight, b.flight) {
        case (.perched, .flying), (.pointing, .flying):
            return [WrenClips.takeoff, WrenClips.holdOff]
        case (.flying, .perched), (.flying, .pointing):
            clips.append(WrenClips.land)
        default:
            break
        }

        if eb == .sleepy && !b.pose.yawn && !(ea == .sleepy && !a.pose.yawn) {
            clips.append(WrenClips.settle)
        } else if ea == .sleepy && eb != .sleepy {
            clips.append(WrenClips.ruffle.mirrored(s))
        }
        if glad.contains(eb) && !glad.contains(ea) {
            clips.append(a.working || a.state == .thinking ? WrenClips.proud : WrenClips.hop)
            if eb == .excited { clips.append(WrenClips.flutter) }
        } else if eb == .excited && ea != .excited {
            clips.append(WrenClips.flutter)
        }
        if eb == .concerned && ea != .concerned { clips.append(WrenClips.flinch.mirrored(-s)) }
        if eb == .sad && ea != .sad { clips.append(WrenClips.deflate) }
        if eb == .confused && ea != .confused { clips.append(WrenClips.doubleTake.mirrored(-s)) }

        if b.state != a.state {
            switch b.state {
            case .listening: clips.append(WrenClips.perk)
            case .dictating: clips.append(WrenClips.nod)
            case .speaking: clips.append(WrenClips.inhale)
            case .thinking, .transcribing: clips.append(WrenClips.hmm.mirrored(s))
            case .idle: if a.state == .speaking { clips.append(WrenClips.settle) }
            }
        }
        if b.asking && !a.asking { clips.append(WrenClips.tailTick); clips.append(WrenClips.perk) }
        if b.working && !a.working { clips.append(WrenClips.rollUp) }

        if let habit = b.pose.habit, habit != a.pose.habit {
            switch habit {
            case .tailFlick: clips.append(WrenClips.tailFlick)
            case .bob: clips.append(WrenClips.bob)
            case .scarfTug: clips.append(WrenClips.scarfTug(near: s))
            case .ruffle: clips.append(WrenClips.ruffle.mirrored(s))
            case .wingStretch: clips.append(WrenClips.wingStretch(near: s))
            }
        }
        if b.pose.squash > 0.06 && a.pose.squash <= 0.06 && b.pose.habit == nil && !b.pose.yawn && b.state == .idle,
           b.pose.squash < 0.085 {
            // the life layer's stretch: a wing goes with it
            clips.append(WrenClips.wingStretch(near: s))
        }
        return clips
    }
}

/// Milo's moves. Values are offsets on the pose channels; times are seconds. Each starts and ends at zero.
enum WrenClips {
    /// A hop for joy: crouch (anticipation), spring up with the wings lifting, land in a squash, settle.
    static let hop = WrenClip("hop", [
        .squash: [(0, 0), (0.09, -0.15), (0.17, 0.13), (0.3, 0.03), (0.39, -0.11), (0.5, 0.035), (0.64, 0)],
        .lift: [(0, 0), (0.1, 0), (0.25, 17), (0.38, 0), (0.64, 0)],
        .wingL: [(0, 0), (0.12, -3), (0.22, 26), (0.36, -5), (0.52, 0)],
        .wingR: [(0, 0), (0.12, -3), (0.22, 26), (0.36, -5), (0.52, 0)],
        .headY: [(0, 0), (0.1, 2), (0.2, -2), (0.4, 2), (0.6, 0)],
    ])

    /// Quietly proud of a job done: chest out, a slow nod, eyes narrowed in a pleased squint.
    static let proud = WrenClip("proud", [
        .squash: [(0, 0), (0.25, 0.06), (0.9, 0.04), (1.3, 0)],
        .headY: [(0, 0), (0.2, -2), (0.45, 3.5), (0.75, -0.5), (1, 0)],
        .lidL: [(0, 0), (0.35, 0.25), (1.1, 0.25), (1.4, 0)],
        .lidR: [(0, 0), (0.35, 0.25), (1.1, 0.25), (1.4, 0)],
        .tail: [(0, 0), (0.3, 12), (1, 8), (1.4, 0)],
    ])

    /// A small nod while you talk to him: "mm-hm".
    static let nod = WrenClip("nod", [
        .headY: [(0, 0), (0.1, 3), (0.26, -0.6), (0.4, 0)],
        .squash: [(0, 0), (0.1, -0.02), (0.3, 0)],
        .headTilt: [(0, 0), (0.12, 1.5), (0.4, 0)],
    ])

    /// "Yes?": a two-beat tail tick while a question waits.
    static let tailTick = WrenClip("tailTick", [
        .tail: [(0, 0), (0.07, 18), (0.16, -4), (0.24, 14), (0.34, -2), (0.5, 0)],
        .tailFan: [(0, 0), (0.08, 0.5), (0.5, 0)],
    ])

    static let tailFlick = WrenClip("tailFlick", [
        .tail: [(0, 0), (0.06, 22), (0.2, -6), (0.4, 0)],
        .tailFan: [(0, 0), (0.06, 0.6), (0.3, 0)],
    ])

    /// The wren bob: two quick knee-dips with the tail flicking up against them.
    static let bob = WrenClip("bob", [
        .squash: [(0, 0), (0.07, -0.07), (0.16, 0.03), (0.26, -0.05), (0.36, 0.015), (0.48, 0)],
        .headY: [(0, 0), (0.08, 2), (0.18, -1), (0.28, 1.5), (0.48, 0)],
        .tail: [(0, 0), (0.08, 12), (0.2, -3), (0.3, 8), (0.5, 0)],
    ])

    /// Pulling back from bad news: a quick flinch away, eyes wide, wings in.
    static let flinch = WrenClip("flinch", [
        .lean: [(0, 0), (0.06, -5), (0.45, 0)],
        .squash: [(0, 0), (0.05, -0.08), (0.15, 0.04), (0.32, 0)],
        .eyeL: [(0, 0), (0.05, 0.15), (0.45, 0)],
        .eyeR: [(0, 0), (0.05, 0.15), (0.45, 0)],
        .wingL: [(0, 0), (0.05, 10), (0.3, 0)],
        .wingR: [(0, 0), (0.05, 10), (0.3, 0)],
        .headY: [(0, 0), (0.05, -2), (0.3, 0)],
    ])

    /// Ears up: a small anticipation dip, then up and alert.
    static let perk = WrenClip("perk", [
        .squash: [(0, 0), (0.06, -0.06), (0.16, 0.07), (0.32, 0)],
        .lift: [(0, 0), (0.08, 0), (0.16, 4), (0.32, 0)],
        .browL: [(0, 0), (0.1, 0.4), (0.4, 0)],
        .browR: [(0, 0), (0.1, 0.4), (0.4, 0)],
        .eyeL: [(0, 0), (0.1, 0.1), (0.35, 0)],
        .eyeR: [(0, 0), (0.1, 0.1), (0.35, 0)],
    ])

    /// A breath in before speaking.
    static let inhale = WrenClip("inhale", [
        .squash: [(0, 0), (0.15, 0.05), (0.32, 0)],
        .headY: [(0, 0), (0.15, -1.5), (0.32, 0)],
    ])

    /// A breath out: sinking back after speaking, or into sleep.
    static let settle = WrenClip("settle", [
        .squash: [(0, 0), (0.12, -0.05), (0.35, 0.012), (0.55, 0)],
        .headY: [(0, 0), (0.15, 1.5), (0.5, 0)],
    ])

    /// Thinking starts: the head goes back a little and over.
    static let hmm = WrenClip("hmm", [
        .headTilt: [(0, 0), (0.2, -5), (0.6, 0)],
        .headY: [(0, 0), (0.15, -1.5), (0.5, 0)],
        .lean: [(0, 0), (0.2, -1.5), (0.6, 0)],
    ])

    /// Taps his tail while he thinks, like drumming fingers.
    static let tap = WrenClip("tap", [
        .tail: [(0, 0), (0.08, 9), (0.2, 0), (0.28, 6), (0.4, 0)],
    ])

    /// A beat of speech: a nod and the brows lifting with it.
    static let emphasis = WrenClip("emphasis", [
        .headY: [(0, 0), (0.08, -1.5), (0.2, 2), (0.4, 0)],
        .browL: [(0, 0), (0.1, 0.35), (0.45, 0)],
        .browR: [(0, 0), (0.1, 0.35), (0.45, 0)],
        .squash: [(0, 0), (0.1, 0.02), (0.3, 0)],
    ])

    /// Talking with his near wing, like a hand.
    static func gesture(near side: Double) -> WrenClip {
        var clip = WrenClip("gesture", [:])
        let (wing, open): (WrenChannel, WrenChannel) = side < 0 ? (.wingR, .openR) : (.wingL, .openL)
        clip.tracks[wing] = keys([(0, 0), (0.18, 22), (0.4, 14), (0.6, 18), (0.85, 0)])
        clip.tracks[open] = keys([(0, 0), (0.18, 0.7), (0.6, 0.65), (0.85, 0)])
        return clip
    }

    /// Wings spread and flutter twice.
    static let flutter = WrenClip("flutter", [
        .openL: [(0, 0), (0.1, 1), (0.6, 1), (0.8, 0)],
        .openR: [(0, 0), (0.1, 1), (0.6, 1), (0.8, 0)],
        .wingL: [(0, 0), (0.15, 32), (0.25, 4), (0.35, 32), (0.45, 4), (0.55, 24), (0.75, 0)],
        .wingR: [(0, 0), (0.15, 32), (0.25, 4), (0.35, 32), (0.45, 4), (0.55, 24), (0.75, 0)],
    ])

    static let deflate = WrenClip("deflate", mode: .target, [
        .squash: [(0, 0), (0.3, -0.05), (0.9, 0)],
        .headY: [(0, 0), (0.3, 2), (1, 0)],
    ])

    /// Confused: the head swings one way, then the other, and comes to rest tilted.
    static let doubleTake = WrenClip("doubleTake", [
        .headTilt: [(0, 0), (0.1, 8), (0.28, -12), (0.5, 0)],
        .headX: [(0, 0), (0.1, 2), (0.28, -1.5), (0.45, 0)],
        .gazeX: [(0, 0), (0.08, 0.5), (0.26, -0.4), (0.45, 0)],
    ])

    /// Shakes himself awake (or just smooths his feathers): a fast wobble that dies out.
    static let ruffle = WrenClip("ruffle", [
        .headX: [(0, 0), (0.06, -2), (0.12, 2), (0.18, -1.5), (0.24, 1), (0.32, 0)],
        .headTilt: [(0, 0), (0.06, -4), (0.12, 4), (0.18, -3), (0.26, 2), (0.36, 0)],
        .squash: [(0, 0), (0.05, 0.06), (0.12, -0.04), (0.2, 0.03), (0.36, 0)],
        .wingL: [(0, 0), (0.06, 8), (0.12, -2), (0.18, 6), (0.3, 0)],
        .wingR: [(0, 0), (0.06, 8), (0.12, -2), (0.18, 6), (0.3, 0)],
        .lidL: [(0, 0), (0.08, 0.5), (0.3, 0.4), (0.45, 0)],
        .lidR: [(0, 0), (0.08, 0.5), (0.3, 0.4), (0.45, 0)],
        .tail: [(0, 0), (0.08, 10), (0.16, -6), (0.24, 4), (0.4, 0)],
    ])

    /// Rolling up his sleeves: tosses the scarf back with a determined little nod.
    static let rollUp = WrenClip("rollUp", [
        .squash: [(0, 0), (0.08, -0.06), (0.2, 0.05), (0.36, 0)],
        .headY: [(0, 0), (0.12, -1.5), (0.26, 2.5), (0.45, 0)],
        .scarf: [(0, 0), (0.1, 12), (0.3, 0)],
    ])

    /// Crouch, then spring into the air with the wings coming up.
    static let takeoff = WrenClip("takeoff", [
        .squash: [(0, 0), (0.1, -0.15), (0.2, 0.15), (0.4, 0)],
        .lift: [(0, 0), (0.12, -1), (0.22, 10), (0.42, 0)],
        .wingL: [(0, 0), (0.1, -10), (0.2, 30), (0.35, 0)],
        .wingR: [(0, 0), (0.1, -10), (0.2, 30), (0.35, 0)],
        .tail: [(0, 0), (0.1, -10), (0.25, 10), (0.4, 0)],
    ])

    /// Keeps him on the ground through the crouch: the wings only come up as he springs.
    static let holdOff = WrenClip("holdOff", mode: .target, [
        .fly: [(0, -1), (0.12, -1), (0.18, 0)],
    ])

    /// Touchdown: a squash on landing, wings out for balance, the tail bouncing.
    static let land = WrenClip("land", [
        .squash: [(0, 0), (0.06, -0.16), (0.18, 0.06), (0.3, -0.03), (0.46, 0)],
        .wingL: [(0, 0), (0.06, 22), (0.25, -4), (0.42, 0)],
        .wingR: [(0, 0), (0.06, 22), (0.25, -4), (0.42, 0)],
        .tail: [(0, 0), (0.08, -12), (0.25, 9), (0.46, 0)],
        .headY: [(0, 0), (0.06, 3), (0.2, -1), (0.36, 0)],
    ])

    /// A wing reaches over and tugs the scarf straight.
    static func scarfTug(near side: Double) -> WrenClip {
        var clip = WrenClip("scarfTug", [
            .scarf: [(0, 0), (0.36, 0), (0.44, -14), (0.62, 6), (0.95, 0)],
            .headY: [(0, 0), (0.3, 1.5), (0.7, 1.5), (0.95, 0)],
            .gazeY: [(0, 0), (0.15, 0.55), (0.75, 0.5), (0.95, 0)],
            .gazeX: [(0, 0), (0.15, 0.35 * -side), (0.75, 0.3 * -side), (0.95, 0)],
        ])
        clip.tracks[side < 0 ? .wingR : .wingL] = keys([(0, 0), (0.22, -62), (0.38, -58), (0.48, -64), (0.85, 0)])
        return clip
    }

    /// One wing stretched out long and folded again, eyes half shut with the pleasure of it.
    static func wingStretch(near side: Double) -> WrenClip {
        var clip = WrenClip("wingStretch", [
            .lidL: [(0, 0), (0.3, 0.3), (0.95, 0.3), (1.2, 0)],
            .lidR: [(0, 0), (0.3, 0.3), (0.95, 0.3), (1.2, 0)],
            .lean: [(0, 0), (0.3, 2 * side), (1.2, 0)],
            .squash: [(0, 0), (0.3, 0.04), (1, 0.02), (1.2, 0)],
        ])
        let (wing, open): (WrenChannel, WrenChannel) = side < 0 ? (.wingR, .openR) : (.wingL, .openL)
        clip.tracks[wing] = keys([(0, 0), (0.3, -12), (0.9, -6), (1.2, 0)])
        clip.tracks[open] = keys([(0, 0), (0.3, 1), (0.9, 1), (1.2, 0)])
        return clip
    }

    private static func keys(_ list: [(Double, Double)]) -> [WrenClip.Key] {
        list.map { WrenClip.Key(at: $0.0, value: $0.1) }
    }
}
