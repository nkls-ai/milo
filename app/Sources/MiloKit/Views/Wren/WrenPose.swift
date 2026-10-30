import CoreGraphics
import Foundation

/// Every number Milo's rig reads. A state is a set of these numbers, and a change of state is the springs
/// moving from one set to the next, so nothing ever pops.
///
/// Figure space is the design page's: a 200-unit box with the ground at y = 182 and his middle at x = 100,
/// y pointing down (docs/design/milo-character.html).
struct WrenPose: Equatable {
    /// -1...1. Negative turns him toward the viewer's left (the screen centre, from the bottom-right corner).
    var turn = -0.2
    /// Degrees clockwise, about his feet.
    var lean = 0.0
    /// Positive is taller and thinner.
    var squash = 0.0
    /// Figure units off the ground.
    var lift = 0.0
    /// Degrees clockwise, about the middle of his face.
    var headTilt = 0.0
    /// The face shifted in figure units: looking, bobbing, nodding.
    var headX = 0.0, headY = 0.0
    /// Where the eyes look, -1...1, x right, y down.
    var gazeX = 0.0, gazeY = 0.0
    /// Upper lids, 0 open ... 1 shut. About 0.2 at rest: calm, a little dry.
    var lidL = 0.2, lidR = 0.2
    /// Lower lids pushing up into a smile, 0...1.
    var lowerL = 0.14, lowerR = 0.14
    var eyeL = 1.0, eyeR = 1.0
    /// Brow stripes raised (+) or lowered, and tilted: + lifts the inner end (worried).
    var browL = 0.0, browR = 0.0
    var browTiltL = 0.0, browTiltR = 0.0
    /// 0 shut ... 1 wide open.
    var beak = 0.0
    /// Pink in his cheeks: always a little, more when he is pleased.
    var blush = 0.3
    /// Degrees, positive raises the wing away from the body.
    var wingL = 0.0, wingR = 0.0
    /// 0 folded ... 1 spread like a hand.
    var openL = 0.0, openR = 0.0
    /// 0 perched ... 1 in the air: wings up, feet tucked, tail streaming.
    var fly = 0.0
    /// Degrees, positive cocks the tail higher; and how far it fans.
    var tail = 0.0, tailFan = 0.0
    /// Degrees the scarf's loose end swings. Driven by the body's motion, never set by a state.
    var scarf = 0.0
    /// 0 hanging ... 1 tossed over his shoulder.
    var scarfToss = 0.0
    /// 0 around his neck ... 1 pulled up over his beak, for sleeping.
    var scarfUp = 0.0
    /// 0 tucked ... 1 standing.
    var feet = 1.0
    /// The tuft on his crown: -1 laid flat (asleep, sad), 0 at rest, 1 perked right up.
    var crest = 0.0
    /// Degrees the tuft sways. Driven by the body's motion, never set by a state.
    var crestSway = 0.0
    /// Breathing, -1...1, for renders; on screen Core Animation breathes him.
    var breath = 0.0

    static let rest = WrenPose()
}

/// The pose numbers by name, each with the spring that moves it. Body parts are slower and heavier than
/// eyes; the tail, scarf and head are loose so they lag the body (overlapping action).
enum WrenChannel: Int, CaseIterable {
    case turn, lean, squash, lift, headTilt, headX, headY, gazeX, gazeY
    case lidL, lidR, lowerL, lowerR, eyeL, eyeR, browL, browR, browTiltL, browTiltR
    case beak, blush, wingL, wingR, openL, openR, fly, tail, tailFan, scarf, scarfToss, scarfUp, feet, crest, crestSway

    var keyPath: WritableKeyPath<WrenPose, Double> {
        switch self {
        case .turn: \.turn
        case .lean: \.lean
        case .squash: \.squash
        case .lift: \.lift
        case .headTilt: \.headTilt
        case .headX: \.headX
        case .headY: \.headY
        case .gazeX: \.gazeX
        case .gazeY: \.gazeY
        case .lidL: \.lidL
        case .lidR: \.lidR
        case .lowerL: \.lowerL
        case .lowerR: \.lowerR
        case .eyeL: \.eyeL
        case .eyeR: \.eyeR
        case .browL: \.browL
        case .browR: \.browR
        case .browTiltL: \.browTiltL
        case .browTiltR: \.browTiltR
        case .beak: \.beak
        case .blush: \.blush
        case .wingL: \.wingL
        case .wingR: \.wingR
        case .openL: \.openL
        case .openR: \.openR
        case .fly: \.fly
        case .tail: \.tail
        case .tailFan: \.tailFan
        case .scarf: \.scarf
        case .scarfToss: \.scarfToss
        case .scarfUp: \.scarfUp
        case .feet: \.feet
        case .crest: \.crest
        case .crestSway: \.crestSway
        }
    }

    /// Seconds to settle (about one period) and damping, 1 = no overshoot.
    var spring: (response: Double, damping: Double) {
        switch self {
        case .gazeX, .gazeY: (0.09, 0.92)          // saccades: fast and clean
        case .lidL, .lidR, .lowerL, .lowerR: (0.12, 0.9)
        case .eyeL, .eyeR: (0.18, 0.7)
        case .browL, .browR, .browTiltL, .browTiltR: (0.2, 0.62)
        case .beak: (0.1, 0.7)                     // follows the voice: quick, but never a snap
        case .blush: (0.6, 1)
        case .squash: (0.2, 0.42)                  // squash and stretch overshoots
        case .lift: (0.26, 0.6)
        case .lean: (0.42, 0.6)
        case .turn: (0.45, 0.85)
        case .headTilt: (0.5, 0.48)                // the head lags the body and settles after it
        case .headX, .headY: (0.32, 0.55)
        case .wingL, .wingR: (0.26, 0.5)
        case .openL, .openR: (0.24, 0.8)
        case .fly: (0.32, 0.85)
        case .tail: (0.38, 0.32)                   // springy: the mood-tail wags into place
        case .tailFan: (0.3, 0.6)
        case .scarf: (0.75, 0.22)                  // a loose knitted end, swinging
        case .scarfToss: (0.36, 0.55)
        case .scarfUp: (0.6, 0.9)
        case .feet: (0.2, 1)
        case .crest: (0.26, 0.5)                   // perks up with a little bounce
        case .crestSway: (0.4, 0.28)               // soft feathers: they wobble after every move
        }
    }

    /// Closer than this to the target, at rest, counts as settled.
    var epsilon: Double {
        switch self {
        case .lean, .headTilt, .wingL, .wingR, .tail, .scarf, .crestSway: 0.05
        case .lift, .headX, .headY: 0.02
        default: 0.002
        }
    }
}

extension WrenPose {
    subscript(channel: WrenChannel) -> Double {
        get { self[keyPath: channel.keyPath] }
        set { self[keyPath: channel.keyPath] = newValue }
    }
}
