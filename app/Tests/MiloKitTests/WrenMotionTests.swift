import CoreGraphics
import Foundation
import Testing
@testable import MiloKit

/// Milo's motion: every change of state blends without a pop, every move ends, and he comes to rest so the
/// frame clock can stop.
@Suite struct WrenMotionTests {
    static let inputs: [(String, FigureInput)] = [
        ("idle", FigureInput()),
        ("listening", FigureInput(state: .listening, level: 0.6, pose: LifePose(lean: -1, tilt: -4))),
        ("dictating", FigureInput(state: .dictating, level: 0.4)),
        ("thinking", FigureInput(state: .thinking, emotion: .thinking, pose: LifePose(gaze: CGVector(dx: 0.7, dy: -0.75)))),
        ("speaking", FigureInput(state: .speaking, level: 0.8)),
        ("working", FigureInput(flight: .pointing(toward: CGVector(dx: -0.6, dy: 0.8)), working: true)),
        ("asking", FigureInput(asking: true)),
        ("happy", FigureInput(emotion: .happy)),
        ("excited", FigureInput(emotion: .excited)),
        ("concerned", FigureInput(emotion: .concerned)),
        ("sad", FigureInput(emotion: .sad)),
        ("confused", FigureInput(emotion: .confused)),
        ("asleep", FigureInput(asleep: true)),
        ("flying", FigureInput(flight: .flying(heading: CGVector(dx: -0.8, dy: -0.6)))),
        ("pointing", FigureInput(flight: .pointing(toward: CGVector(dx: -0.97, dy: -0.24)))),
        ("habit", FigureInput(pose: LifePose(habit: .bob))),
        ("turned", FigureInput(pose: LifePose(side: 1))),
        ("noting", FigureInput(noting: true)),
        ("noting, talked to", FigureInput(state: .listening, level: 0.5, noting: true)),
    ]

    /// The most any channel moves in one 60 fps frame, as a share of its usual range.
    static let range: [WrenChannel: Double] = [
        .turn: 0.6, .lean: 20, .squash: 0.4, .lift: 30, .headTilt: 25, .headX: 6, .headY: 6, .gazeX: 2, .gazeY: 2,
        .lidL: 1, .lidR: 1, .lowerL: 1, .lowerR: 1, .eyeL: 0.3, .eyeR: 0.3, .browL: 1.5, .browR: 1.5,
        .browTiltL: 1.5, .browTiltR: 1.5, .beak: 1, .blush: 1, .wingL: 120, .wingR: 120, .openL: 1, .openR: 1,
        .fly: 1, .tail: 60, .tailFan: 1, .scarf: 100, .scarfToss: 1, .scarfUp: 1, .feet: 1, .crest: 2, .crestSway: 60,
        .pad: 1, .pen: 2.4,
    ]

    @Test func everyChangeOfStateBlendsWithoutAPop() {
        for (fromName, from) in Self.inputs {
            for (toName, to) in Self.inputs where toName != fromName {
                var director = WrenDirector(seed: 1)
                var motion = WrenMotion()
                director.direct(from, motion: &motion, at: 0)
                motion.snap()
                var last = motion.pose
                director.direct(to, motion: &motion, at: 0)
                for frame in 1...90 {
                    motion.advance(by: 1.0 / 60)
                    director.direct(to, motion: &motion, at: Double(frame) / 60)
                    let now = motion.pose
                    for c in WrenChannel.allCases where c != .lidL && c != .lidR {
                        // Wingbeats are meant to be fast, and the beak opens with a syllable over two or three
                        // frames, like drawn lip sync; everything else moves at most a third of its range a frame.
                        if (c == .wingL || c == .wingR || c == .scarf || c == .lift) && (now.fly > 0.05 || last.fly > 0.05) { continue }
                        let step = abs(now[c] - last[c]) / Self.range[c]!
                        #expect(step < (c == .beak ? 0.5 : 0.35), "\(fromName) → \(toName): \(c) jumped \(now[c] - last[c]) at frame \(frame)")
                    }
                    last = now
                }
            }
        }
    }

    @Test func everyStateComesToRestSoTheFrameClockStops() {
        for (name, input) in Self.inputs where name != "flying" {
            var director = WrenDirector(seed: 2)
            var motion = WrenMotion()
            director.direct(FigureInput(), motion: &motion, at: 0)
            motion.snap()
            director.direct(input, motion: &motion, at: 0)
            var t = 0.0
            // Rhythms (a speaking gesture, a thinking tap) restart motion on their beat; between beats he rests.
            while t < 6, !motion.settled || director.wake <= t {
                t += 1.0 / 60
                if director.wake <= t { director.direct(input, motion: &motion, at: t) }
                motion.advance(by: 1.0 / 60)
                if motion.settled && director.wake > t + 0.1 { break }
            }
            #expect(motion.settled, "\(name) still moving after \(t) s: \(motion.playing)")
            #expect(motion.pose == motion.target || name == "flying", "\(name) rests on its pose")
        }
    }

    @Test func flyingKeepsFlappingUntilHeLands() {
        var director = WrenDirector(seed: 3)
        var motion = WrenMotion()
        director.direct(FigureInput(), motion: &motion, at: 0)
        motion.snap()
        let flying = FigureInput(flight: .flying(heading: CGVector(dx: -1, dy: 0)))
        director.direct(flying, motion: &motion, at: 0)
        var wings: [Double] = []
        for i in 0..<120 { motion.advance(by: 1.0 / 60); director.direct(flying, motion: &motion, at: Double(i) / 60); wings.append(motion.pose.wingL) }
        #expect(!motion.settled)
        #expect((wings.max() ?? 0) - (wings.min() ?? 0) > 40, "the wings beat")
        #expect(motion.playing.isEmpty, "the takeoff ends")
        director.direct(FigureInput(flight: .perched), motion: &motion, at: 2)
        #expect(motion.playing.contains("land"))
        for _ in 0..<240 { motion.advance(by: 1.0 / 60) }
        #expect(motion.settled && motion.pose.fly == 0)
    }

    @Test func aBlinkShutsTheEyesBrieflyAndOpensThemAgain() {
        var director = WrenDirector(seed: 4)
        var motion = WrenMotion()
        director.direct(FigureInput(), motion: &motion, at: 0)
        motion.snap()
        director.direct(FigureInput(pose: LifePose(blink: true)), motion: &motion, at: 0)
        var lids: [Double] = []
        for _ in 0..<20 { motion.advance(by: 1.0 / 60); lids.append(motion.pose.lidL) }
        #expect(lids.max()! > 0.99, "shut")
        let shut = lids.filter { $0 > 0.9 }.count
        #expect(shut >= 2 && shut <= 6, "held about 70 ms, not \(shut) frames")
        #expect(abs(lids.last! - WrenPose.rest.lidL) < 0.01, "open again")
        #expect(motion.settled)
    }

    @Test func theTailAndScarfLagTheBody() {
        var motion = WrenMotion()
        motion.play(WrenClips.hop)
        var scarf: [Double] = [], tail: [Double] = []
        for _ in 0..<90 { motion.advance(by: 1.0 / 60); scarf.append(motion.pose.scarf); tail.append(motion.pose.tail) }
        #expect(scarf.map(abs).max()! > 3, "the scarf swings")
        #expect(tail.map(abs).max()! > 2, "the tail whips")
        // they keep moving after the hop's last key (follow-through), then settle
        let hopEnd = Int(WrenClips.hop.duration * 60)
        #expect(scarf[hopEnd...].map(abs).max()! > 0.5)
        for _ in 0..<300 { motion.advance(by: 1.0 / 60) }
        #expect(motion.settled)
    }

    @Test func speakingOpensTheBeakWithTheVoice() {
        var director = WrenDirector(seed: 5)
        var motion = WrenMotion()
        director.direct(FigureInput(state: .speaking, level: 0), motion: &motion, at: 0)
        motion.snap()
        director.direct(FigureInput(state: .speaking, level: 0.9), motion: &motion, at: 0)
        for _ in 0..<8 { motion.advance(by: 1.0 / 60) }
        #expect(motion.pose.beak > 0.6)
        director.direct(FigureInput(state: .speaking, level: 0), motion: &motion, at: 0.14)
        for _ in 0..<8 { motion.advance(by: 1.0 / 60) }
        #expect(motion.pose.beak < 0.15)
    }

    @Test func reduceMotionDropsTheMovesButKeepsThePose() {
        var director = WrenDirector(seed: 6)
        var motion = WrenMotion()
        director.direct(FigureInput(), motion: &motion, at: 0, reduceMotion: true)
        director.direct(FigureInput(emotion: .happy), motion: &motion, at: 0, reduceMotion: true)
        #expect(motion.playing.isEmpty)
        #expect(motion.target.lowerL == 1)
    }
}
