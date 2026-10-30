import SwiftUI

enum DragonPalette {
    static let bodyLight = Color(red: 0.58, green: 0.86, blue: 0.67)
    static let bodyDark = Color(red: 0.24, green: 0.62, blue: 0.47)
    static let limb = Color(red: 0.30, green: 0.68, blue: 0.51)
    static let limbDark = Color(red: 0.19, green: 0.50, blue: 0.38)
    static let muzzle = Color(red: 0.80, green: 0.95, blue: 0.81)
    static let bellyLight = Color(red: 1.0, green: 0.96, blue: 0.84)
    static let bellyDark = Color(red: 0.96, green: 0.84, blue: 0.62)
    static let plate = Color(red: 0.86, green: 0.70, blue: 0.47)
    static let horn = Color(red: 1.0, green: 0.95, blue: 0.85)
    static let hornDark = Color(red: 0.89, green: 0.76, blue: 0.58)
    static let membrane = Color(red: 1.0, green: 0.66, blue: 0.53)
    static let membraneDark = Color(red: 0.93, green: 0.46, blue: 0.42)
    static let eye = Color(red: 0.11, green: 0.16, blue: 0.17)
    static let mouth = Color(red: 0.36, green: 0.16, blue: 0.20)
    static let tongue = Color(red: 1.0, green: 0.55, blue: 0.60)
    static let cheek = Color(red: 1.0, green: 0.56, blue: 0.62)
    static let smoke = Color(red: 0.86, green: 0.88, blue: 0.91)
    static let spark = Color(red: 1.0, green: 0.70, blue: 0.24)
    static let sparkCore = Color(red: 1.0, green: 0.93, blue: 0.60)
}

/// A small round dragon: a big head with a soft snout and two little horns, a round belly, stubby arms,
/// tiny coral wings and a tail with a spade at the end. He puffs smoke while he thinks, a spark flies when
/// he's excited, and he sleeps curled around his tail. Feet on y = 107, like the other skins.
struct DragonFigure: Skin {
    var look: SkinLook

    static func idleLoop(_ look: SkinLook) -> Loop? {
        guard !look.airborne else { return nil }
        let feet = UnitPoint(x: 0.5, y: 107 / 120)
        if look.sleeping { return .breath(period: 5, amount: 0.03, pivot: feet) }
        return .breath(period: 3.4, amount: 0.014, pivot: feet)
    }

    var body: some View {
        ZStack {
            ListeningRing(look: look, center: CGPoint(x: 60, y: 62), diameter: 108)
            GroundShadow(look: look, width: look.sleeping ? 66 : 54, y: 108.5)
            DragonBody(look: look)
            if look.thinking && !look.airborne {
                Smoke(look: look)
            }
            if look.emotion == .excited && !look.airborne {
                Spark(look: look)
            }
            Marks(look: look, at: CGPoint(x: 102, y: 20), sleepColor: DragonPalette.bodyDark)
        }
        .frame(width: 120, height: 120)
    }
}

/// The dragon's own reading of the look.
private struct DragonPose {
    var look: SkinLook

    var sleeping: Bool { look.sleeping }
    var curled: Bool { look.sleeping && !look.airborne }

    /// Wing angle in degrees around the shoulder, positive lifts the left wing (mirrored for the right).
    var wingLift: Double {
        switch look.flight {
        case .flying: return 10
        case .pointing: return 8
        case .perched: break
        }
        if curled { return -20 }
        if look.happy { return 16 }
        if look.listening { return 8 }
        if look.emotion == .sad || look.emotion == .concerned { return -16 }
        return -4
    }

    /// Wings grow while he flies, so tiny wings can carry him.
    var wingScale: Double { look.airborne ? 1.5 : 1 }

    /// Arm angles in degrees around the shoulder, clockwise; zero hangs straight down.
    var arms: (left: Double, right: Double, leftLength: Double, rightLength: Double) {
        switch look.flight {
        case .flying:
            return (35, -35, 0.85, 0.85)
        case let .pointing(toward):
            let angle = atan2(-toward.dx, toward.dy) * 180 / .pi
            if toward.dx <= 0 { return (angle, -30, 1.7, 1) }
            return (30, angle - 360 * (angle > 0 ? 1 : 0), 1, 1.7)
        case .perched:
            break
        }
        if curled { return (-34, 34, 0.8, 0.8) }
        if look.emotion == .excited { return (150, -150, 1, 1) }
        if look.happy { return (120, -120, 1, 1) }
        if look.thinking { return (-30, -150, 1, 1) }
        if look.emotion == .concerned || look.emotion == .sad { return (-40, 40, 1, 1) }
        return (-28, 28, 1, 1)
    }

    /// The tail's swing around its root while perched: a slow sway, a wag when he's pleased.
    var tailLoop: Loop? {
        guard !look.airborne, !curled else { return nil }
        let root = UnitPoint(x: 80 / 120, y: 96 / 120)
        if look.happy {
            return Loop(period: 0.45, keys: [.init(at: 0, angle: -10), .init(at: 0.5, angle: 6), .init(at: 1, angle: -10)],
                        pivot: root)
        }
        return Loop(period: 4.2, keys: [.init(at: 0, angle: -4), .init(at: 0.5, angle: 3), .init(at: 1, angle: -4)],
                    pivot: root)
    }

    func wingLoop(left: Bool) -> Loop? {
        let sign = left ? 1.0 : -1.0
        let shoulder = UnitPoint(x: left ? 1 : 0, y: 1)
        switch look.flight {
        case .flying:
            return Loop(period: 1 / 5, keys: [.init(at: 0, angle: 30 * sign, opacity: 1), .init(at: 0.5, angle: -40 * sign),
                                              .init(at: 1, angle: 30 * sign)], pivot: shoulder)
        case .pointing:
            return Loop(period: 0.55, keys: [.init(at: 0, angle: 10 * sign), .init(at: 0.5, angle: -14 * sign),
                                             .init(at: 1, angle: 10 * sign)], pivot: shoulder)
        case .perched where look.emotion == .excited:
            return Loop(period: 0.3, keys: [.init(at: 0, angle: 8 * sign), .init(at: 0.5, angle: -6 * sign),
                                            .init(at: 1, angle: 8 * sign)], pivot: shoulder)
        default:
            return nil
        }
    }
}

private struct DragonBody: View {
    var look: SkinLook

    var body: some View {
        let pose = DragonPose(look: look)
        let gaze = look.gaze
        let stretch = look.stretch - (pose.curled ? 0.04 : 0)
        ZStack {
            if !pose.curled {
                Looping(pose.tailLoop, frozen: look.frozen, time: look.time) {
                    DragonTail(look: look).frame(width: 120, height: 120)
                }
                .frame(width: 120, height: 120)
            }
            wing(left: true, pose: pose)
            wing(left: false, pose: pose)
            feet
            torso
            if pose.curled {
                CurledTail(look: look)
            }
            arm(left: true, pose: pose)
            arm(left: false, pose: pose)
            DragonHead(look: look)
                .offset(x: gaze.dx * 2.5 + (pose.curled ? -4 : 0), y: gaze.dy * 1.5 + (pose.curled ? 12 : 0))
                .rotationEffect(.degrees(pose.curled ? -10 : 0), anchor: UnitPoint(x: 0.5, y: 0.55))
        }
        .frame(width: 120, height: 120)
        .scaleEffect(x: 1 - stretch * 0.6, y: 1 + stretch, anchor: UnitPoint(x: 0.5, y: 107 / 120))
        .rotationEffect(.degrees(look.tilt), anchor: UnitPoint(x: 0.5, y: 107 / 120))
        .offset(x: look.airborne ? 0 : look.pose.lean * 3, y: look.lift)
        .animation(.spring(response: 0.22, dampingFraction: 0.5), value: look.pose.squash)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.pose.lean)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: look.pose.tilt)
        .animation(.spring(response: 0.25, dampingFraction: 0.8), value: look.pose.gaze)
        .animation(.spring(response: 0.4, dampingFraction: 0.75), value: look.emotion)
        .animation(.spring(response: 0.4, dampingFraction: 0.75), value: look.state)
        .animation(.spring(response: 0.35, dampingFraction: 0.7), value: look.flight)
        .animation(.easeOut(duration: 0.08), value: look.level)
    }

    private func wing(left: Bool, pose: DragonPose) -> some View {
        let size = CGSize(width: 29 * pose.wingScale, height: 24 * pose.wingScale)
        let shoulder = CGPoint(x: left ? 43 : 77, y: 74)
        return Looping(pose.wingLoop(left: left), frozen: look.frozen, time: look.time) {
            DragonWing(look: look)
                .scaleEffect(x: left ? 1 : -1)
                .frame(width: size.width, height: size.height)
        }
        .frame(width: size.width, height: size.height)
        .rotationEffect(.degrees(pose.wingLift * (left ? 1 : -1)), anchor: left ? .bottomTrailing : .bottomLeading)
        .opacity(pose.curled ? 0 : 1)
        .position(x: shoulder.x + (left ? -size.width / 2 : size.width / 2), y: shoulder.y - size.height / 2)
    }

    private var feet: some View {
        ZStack {
            ForEach([true, false], id: \.self) { left in
                ZStack {
                    Ellipse()
                        .fill(LinearGradient(colors: [DragonPalette.limb, DragonPalette.limbDark], startPoint: .top, endPoint: .bottom))
                        .frame(width: 17, height: 10)
                    if !look.small {
                        HStack(spacing: 2.2) {
                            ForEach(0..<3, id: \.self) { _ in
                                Capsule().fill(DragonPalette.horn).frame(width: 2.6, height: 2.2)
                            }
                        }
                        .offset(y: 3.4)
                    }
                }
                .position(x: left ? 48 : 72, y: 104)
            }
        }
        .opacity(look.airborne ? 0.9 : 1)
        .offset(y: look.airborne ? 3 : 0)
        .opacity(look.sleeping ? 0 : 1)
    }

    /// The round belly under the head.
    private var torso: some View {
        ZStack {
            Pear()
                .fill(RadialGradient(colors: [DragonPalette.bodyLight, DragonPalette.bodyDark],
                                     center: UnitPoint(x: 0.4, y: 0.25), startRadius: 3, endRadius: 52))
            Ellipse()
                .fill(LinearGradient(colors: [DragonPalette.bellyLight, DragonPalette.bellyDark], startPoint: .top, endPoint: .bottom))
                .frame(width: 36, height: 34)
                .position(x: 29, y: 30)
            if !look.small {
                BellyPlates()
                    .stroke(DragonPalette.plate.opacity(0.75), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
                    .frame(width: 28, height: 24)
                    .position(x: 29, y: 31)
            }
        }
        .frame(width: 58, height: 50)
        .clipShape(Pear())
        .shadow(color: DragonPalette.bodyDark.opacity(look.small ? 0 : 0.3), radius: 5, y: 3)
        .scaleEffect(x: 1 + (look.speaking ? look.level * 0.02 : 0), anchor: .bottom)
        .position(x: 60, y: 82)
    }

    private func arm(left: Bool, pose: DragonPose) -> some View {
        let arms = pose.arms
        let angle = left ? arms.left : arms.right
        let length = 15 * (left ? arms.leftLength : arms.rightLength)
        return ZStack(alignment: .bottom) {
            Capsule()
                .fill(LinearGradient(colors: [DragonPalette.limb, DragonPalette.bodyLight], startPoint: .top, endPoint: .bottom))
            if !look.small {
                HStack(spacing: 1.4) {
                    ForEach(0..<3, id: \.self) { _ in Capsule().fill(DragonPalette.horn).frame(width: 1.8, height: 2.4) }
                }
                .offset(y: 1.2)
            }
        }
        .frame(width: 9.5, height: length)
        .rotationEffect(.degrees(angle), anchor: .top)
        .position(x: left ? 41 : 79, y: 72 + length / 2)
    }
}

/// The head: wide and round, a pale snout with two nostrils, big eyes, horns and little fin ears.
private struct DragonHead: View {
    var look: SkinLook

    var body: some View {
        let emotion = look.emotion
        let perk: Double = look.listening ? -12 : (emotion == .sad ? 18 : (look.sleeping ? 34 : 0))
        ZStack {
            ForEach([true, false], id: \.self) { left in
                Horn()
                    .fill(LinearGradient(colors: [DragonPalette.horn, DragonPalette.hornDark], startPoint: .top, endPoint: .bottom))
                    .frame(width: 11, height: 18)
                    .rotationEffect(.degrees(left ? -20 : 20), anchor: .bottom)
                    .position(x: left ? 44 : 76, y: 15)
                FinEar()
                    .fill(LinearGradient(colors: [DragonPalette.membrane, DragonPalette.membraneDark], startPoint: .top, endPoint: .bottom))
                    .frame(width: 13, height: 17)
                    .scaleEffect(x: left ? 1 : -1)
                    .rotationEffect(.degrees((left ? -1 : 1) * (28 + perk)), anchor: .bottom)
                    .position(x: left ? 25 : 95, y: 34)
            }
            DragonHeadShape()
                .fill(RadialGradient(colors: [DragonPalette.bodyLight, DragonPalette.bodyDark],
                                     center: UnitPoint(x: 0.38, y: 0.2), startRadius: 3, endRadius: 64))
                .frame(width: 74, height: 56)
                .position(x: 60, y: 42)
            Ellipse()
                .fill(Color.white.opacity(0.26))
                .frame(width: 18, height: 7)
                .rotationEffect(.degrees(-18))
                .blur(radius: look.small ? 0 : 1)
                .position(x: 41, y: 22)
            Ellipse()
                .fill(LinearGradient(colors: [DragonPalette.muzzle, DragonPalette.muzzle.opacity(0.85)], startPoint: .top, endPoint: .bottom))
                .frame(width: 38, height: 22)
                .position(x: 60, y: 58)
            ForEach([true, false], id: \.self) { left in
                Ellipse()
                    .fill(DragonPalette.cheek.opacity(look.happy ? 0.6 : 0.38))
                    .frame(width: 9, height: 5)
                    .blur(radius: look.small ? 0 : 0.7)
                    .position(x: left ? 34 : 86, y: 52)
                Capsule()
                    .fill(DragonPalette.limbDark.opacity(0.75))
                    .frame(width: 2.6, height: 1.9)
                    .rotationEffect(.degrees(left ? 20 : -20))
                    .position(x: left ? 55 : 65, y: 53)
                DragonEye(look: look, left: left)
                    .offset(x: look.gaze.dx * 2.2, y: look.gaze.dy * 1.8)
                    .position(x: left ? 45 : 75, y: 41)
                DragonBrow(emotion: emotion, left: left)
                    .position(x: left ? 44 : 76, y: 31)
            }
            DragonMouth(look: look)
                .position(x: 60, y: 63)
        }
        .frame(width: 120, height: 120)
    }
}

private struct DragonEye: View {
    var look: SkinLook
    var left: Bool

    var body: some View {
        let emotion = look.emotion
        ZStack {
            if look.pose.yawn || emotion == .sleepy {
                ArcShape(up: false)
                    .stroke(DragonPalette.eye, style: StrokeStyle(lineWidth: 2.4, lineCap: .round))
                    .frame(width: 10, height: 2.6)
            } else if emotion == .happy {
                ArcShape(up: true)
                    .stroke(DragonPalette.eye, style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
                    .frame(width: 10, height: 4.2)
                    .offset(y: 1)
            } else {
                let size = eyeSize
                Ellipse()
                    .fill(DragonPalette.eye)
                    .frame(width: size.width, height: look.pose.blink ? 1.6 : size.height)
                    .overlay(alignment: .topTrailing) {
                        Circle().fill(.white).frame(width: size.width * 0.4)
                            .offset(x: -size.width * 0.12, y: size.height * 0.12)
                            .opacity(look.pose.blink ? 0 : 1)
                    }
                    .overlay(alignment: .bottomLeading) {
                        Circle().fill(.white.opacity(0.7)).frame(width: size.width * 0.18)
                            .offset(x: size.width * 0.2, y: -size.height * 0.16)
                            .opacity(look.pose.blink || look.small ? 0 : 1)
                    }
                    .offset(y: emotion == .sad ? 1 : 0)
            }
        }
        .frame(width: 16, height: 16)
        .animation(.easeInOut(duration: 0.07), value: look.pose.blink)
    }

    private var eyeSize: CGSize {
        switch look.emotion {
        case .excited: CGSize(width: 11.5, height: 12.5)
        case .confused: left ? CGSize(width: 10.5, height: 11.5) : CGSize(width: 7, height: 7.5)
        case .sad, .concerned: CGSize(width: 9, height: 9)
        default: look.listening ? CGSize(width: 10.5, height: 11.5) : CGSize(width: 9.6, height: 10.6)
        }
    }
}

/// Soft brow ridges, shown only when a feeling needs them.
private struct DragonBrow: View {
    var emotion: Emotion
    var left: Bool

    var body: some View {
        let tilt: Double = switch emotion {
        case .concerned, .sad: left ? -18 : 18
        case .confused: left ? -6 : 14
        case .thinking: left ? 8 : -8
        default: 0
        }
        Capsule()
            .fill(DragonPalette.limbDark.opacity(0.8))
            .frame(width: 10, height: 2.6)
            .rotationEffect(.degrees(tilt))
            .offset(y: emotion == .thinking ? -1.5 : 0)
            .opacity([.concerned, .sad, .confused, .thinking].contains(emotion) ? 1 : 0)
    }
}

private struct DragonMouth: View {
    var look: SkinLook

    var body: some View {
        let open = look.mouthOpen
        ZStack {
            if open > 0.05 {
                Ellipse()
                    .fill(DragonPalette.mouth)
                    .frame(width: 9 + open * 3, height: 2 + open * 8)
                    .overlay(alignment: .bottom) {
                        Ellipse().fill(DragonPalette.tongue).frame(width: 6 + open * 2, height: 1 + open * 3.5)
                            .offset(y: -0.5)
                    }
                    .clipShape(Ellipse())
                    .offset(y: 1 + open * 3)
            } else {
                switch look.emotion {
                case .happy:
                    SmileShape().fill(DragonPalette.mouth).frame(width: 11, height: 5).offset(y: 1)
                case .sad, .concerned:
                    ArcShape(up: true)
                        .stroke(DragonPalette.mouth, style: StrokeStyle(lineWidth: 1.8, lineCap: .round))
                        .frame(width: 8, height: 2.5).offset(y: 2)
                case .confused:
                    WavyShape()
                        .stroke(DragonPalette.mouth, style: StrokeStyle(lineWidth: 1.6, lineCap: .round))
                        .frame(width: 9, height: 3)
                case .sleepy:
                    Capsule().fill(DragonPalette.mouth.opacity(0.7)).frame(width: 4, height: 1.6)
                default:
                    // A small cat-like "w".
                    MouthW()
                        .stroke(DragonPalette.mouth, style: StrokeStyle(lineWidth: 1.7, lineCap: .round, lineJoin: .round))
                        .frame(width: 10, height: 3.2)
                }
            }
        }
        .frame(width: 16, height: 14)
        .animation(.easeOut(duration: 0.07), value: open)
    }
}

/// The tail behind him: out to the right, up, and a spade at the tip, with three little spikes.
private struct DragonTail: View {
    var look: SkinLook

    var body: some View {
        let flying = look.airborne
        ZStack {
            TaperedCurve(points: [CGPoint(x: 78 / 120.0, y: 98 / 120.0), CGPoint(x: 100 / 120.0, y: 102 / 120.0),
                                  CGPoint(x: 112 / 120.0, y: 92 / 120.0), CGPoint(x: 111 / 120.0, y: 71 / 120.0)],
                         start: 15, end: 4)
                .fill(LinearGradient(colors: [DragonPalette.bodyLight, DragonPalette.bodyDark], startPoint: .top, endPoint: .bottom))
            ForEach(0..<3, id: \.self) { i in
                Spike()
                    .fill(DragonPalette.membrane)
                    .frame(width: 5, height: 5)
                    .rotationEffect(.degrees([18.0, 45, 75][i]))
                    .position(x: [95.0, 105, 110][i], y: [94.0, 88, 79][i])
                    .opacity(look.small ? 0 : 1)
            }
            Spade()
                .fill(LinearGradient(colors: [DragonPalette.membrane, DragonPalette.membraneDark], startPoint: .top, endPoint: .bottom))
                .frame(width: 13, height: 13)
                .rotationEffect(.degrees(3))
                .position(x: 111, y: 66)
        }
        .rotationEffect(.degrees(flying ? -25 : 0), anchor: UnitPoint(x: 80 / 120, y: 96 / 120))
    }
}

/// Asleep, the tail wraps round in front of his feet, with the spade by his cheek.
private struct CurledTail: View {
    var look: SkinLook

    var body: some View {
        ZStack {
            TaperedCurve(points: [CGPoint(x: 86 / 120.0, y: 90 / 120.0), CGPoint(x: 96 / 120.0, y: 112 / 120.0),
                                  CGPoint(x: 40 / 120.0, y: 116 / 120.0), CGPoint(x: 27 / 120.0, y: 97 / 120.0)],
                         start: 15, end: 5)
                .fill(LinearGradient(colors: [DragonPalette.bodyLight, DragonPalette.limb], startPoint: .top, endPoint: .bottom))
            ForEach(0..<3, id: \.self) { i in
                Spike()
                    .fill(DragonPalette.membrane)
                    .frame(width: 5, height: 5)
                    .rotationEffect(.degrees([150.0, 175, 205][i]))
                    .position(x: [80.0, 62, 44][i], y: [111.0, 113.5, 110][i])
                    .opacity(look.small ? 0 : 1)
            }
            Spade()
                .fill(LinearGradient(colors: [DragonPalette.membrane, DragonPalette.membraneDark], startPoint: .top, endPoint: .bottom))
                .frame(width: 12, height: 12)
                .rotationEffect(.degrees(-30))
                .position(x: 25, y: 91)
        }
    }
}

/// While he thinks, small puffs of smoke rise from his nose and fade; asleep, a slow wisp.
private struct Smoke: View {
    var look: SkinLook

    var body: some View {
        let count = 3
        let period = 2.4
        ZStack {
            ForEach(0..<count, id: \.self) { i in
                Looping(Self.puff(period: period, phase: Double(i) * period / Double(count), drift: i == 1 ? 1.2 : 1),
                        frozen: look.frozen, time: look.time) {
                    ZStack {
                        Circle().fill(DragonPalette.smoke).frame(width: 9, height: 9)
                        Circle().fill(DragonPalette.smoke).frame(width: 7, height: 7).offset(x: 4.5, y: 2)
                        Circle().fill(DragonPalette.smoke).frame(width: 6, height: 6).offset(x: -4, y: 2.5)
                        Circle().fill(Color.white.opacity(0.7)).frame(width: 3.5, height: 3.5).offset(x: -1.5, y: -1.5)
                    }
                    .frame(width: 26, height: 26)
                }
                .frame(width: 26, height: 26)
                .position(x: 55 + look.gaze.dx * 2.5, y: 55)
            }
        }
        .frame(width: 120, height: 120)
        .allowsHitTesting(false)
    }

    /// Out of the nose, off to his left past the cheek, then up and away.
    static func puff(period: Double, phase: Double, drift: Double) -> Loop {
        Loop(period: period, keys: [.init(at: 0, dx: 0, dy: 0, sx: 0.25, sy: 0.25, opacity: 0),
                                    .init(at: 0.12, dx: -9, dy: 1, sx: 0.45, sy: 0.45, opacity: 0.4),
                                    .init(at: 0.3, dx: -22 * drift, dy: -4, sx: 0.75, sy: 0.75, opacity: 0.95),
                                    .init(at: 1, dx: -36 * drift, dy: -38, sx: 1.3, sy: 1.3, opacity: 0)],
             smooth: false, phase: phase)
    }
}

/// When he's excited, a tiny spark flickers just off his snout.
private struct Spark: View {
    var look: SkinLook

    var body: some View {
        Looping(Loop(period: 0.7, keys: [.init(at: 0, dx: 0, dy: 0, sx: 0.7, sy: 0.7, angle: -10, opacity: 0.6),
                                         .init(at: 0.4, dx: -1, dy: -3, sx: 1.15, sy: 1.15, angle: 8, opacity: 1),
                                         .init(at: 1, dx: 0, dy: 0, sx: 0.7, sy: 0.7, angle: -10, opacity: 0.6)]),
                frozen: look.frozen, time: look.time) {
            ZStack {
                Flame().fill(DragonPalette.spark).frame(width: 13, height: 18)
                    .shadow(color: DragonPalette.spark.opacity(0.7), radius: 3)
                Flame().fill(DragonPalette.sparkCore).frame(width: 6.5, height: 9.5).offset(y: 3.5)
            }
            .frame(width: 26, height: 26)
        }
        .frame(width: 26, height: 26)
        .position(x: 86, y: 70)
    }
}

// MARK: Shapes

/// A wide, soft head: fuller at the cheeks, a gently domed top and a rounder chin.
private struct DragonHeadShape: Shape {
    func path(in r: CGRect) -> Path {
        let w = r.width, h = r.height, x = r.minX, y = r.minY
        var p = Path()
        p.move(to: CGPoint(x: x + w / 2, y: y))
        p.addCurve(to: CGPoint(x: x + w, y: y + h * 0.55), control1: CGPoint(x: x + w * 0.86, y: y),
                   control2: CGPoint(x: x + w, y: y + h * 0.22))
        p.addCurve(to: CGPoint(x: x + w / 2, y: y + h), control1: CGPoint(x: x + w, y: y + h * 0.88),
                   control2: CGPoint(x: x + w * 0.8, y: y + h))
        p.addCurve(to: CGPoint(x: x, y: y + h * 0.55), control1: CGPoint(x: x + w * 0.2, y: y + h),
                   control2: CGPoint(x: x, y: y + h * 0.88))
        p.addCurve(to: CGPoint(x: x + w / 2, y: y), control1: CGPoint(x: x, y: y + h * 0.22),
                   control2: CGPoint(x: x + w * 0.14, y: y))
        p.closeSubpath()
        return p
    }
}

/// A belly that sits: narrow shoulders, round at the bottom.
private struct Pear: Shape {
    func path(in r: CGRect) -> Path {
        let w = r.width, h = r.height, x = r.minX, y = r.minY
        var p = Path()
        p.move(to: CGPoint(x: x + w / 2, y: y))
        p.addCurve(to: CGPoint(x: x + w, y: y + h * 0.66), control1: CGPoint(x: x + w * 0.78, y: y),
                   control2: CGPoint(x: x + w, y: y + h * 0.3))
        p.addCurve(to: CGPoint(x: x + w / 2, y: y + h), control1: CGPoint(x: x + w, y: y + h * 0.92),
                   control2: CGPoint(x: x + w * 0.78, y: y + h))
        p.addCurve(to: CGPoint(x: x, y: y + h * 0.66), control1: CGPoint(x: x + w * 0.22, y: y + h),
                   control2: CGPoint(x: x, y: y + h * 0.92))
        p.addCurve(to: CGPoint(x: x + w / 2, y: y), control1: CGPoint(x: x, y: y + h * 0.3),
                   control2: CGPoint(x: x + w * 0.22, y: y))
        p.closeSubpath()
        return p
    }
}

/// Three soft bands across the belly.
private struct BellyPlates: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        for (fy, inset) in [(0.25, 0.18), (0.55, 0.06), (0.85, 0.16)] {
            let y = r.minY + r.height * fy
            p.move(to: CGPoint(x: r.minX + r.width * inset, y: y))
            p.addQuadCurve(to: CGPoint(x: r.maxX - r.width * inset, y: y), control: CGPoint(x: r.midX, y: y + r.height * 0.12))
        }
        return p
    }
}

/// A small curved horn, base at the bottom.
private struct Horn: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.maxY))
        p.addCurve(to: CGPoint(x: r.midX + r.width * 0.1, y: r.minY), control1: CGPoint(x: r.minX, y: r.midY),
                   control2: CGPoint(x: r.midX - r.width * 0.15, y: r.minY + r.height * 0.15))
        p.addQuadCurve(to: CGPoint(x: r.midX + r.width * 0.35, y: r.minY + r.height * 0.12),
                       control: CGPoint(x: r.midX + r.width * 0.3, y: r.minY - r.height * 0.04))
        p.addCurve(to: CGPoint(x: r.maxX, y: r.maxY), control1: CGPoint(x: r.midX + r.width * 0.3, y: r.midY * 0.9),
                   control2: CGPoint(x: r.maxX, y: r.midY))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.maxY), control: CGPoint(x: r.midX, y: r.maxY + r.height * 0.1))
        p.closeSubpath()
        return p
    }
}

/// A fin ear on the side of the head, drawn for the left side: base at the bottom right, two points outward.
private struct FinEar: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.maxX, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.minX + r.width * 0.15, y: r.minY), control: CGPoint(x: r.minX + r.width * 0.5, y: r.minY + r.height * 0.45))
        p.addQuadCurve(to: CGPoint(x: r.minX + r.width * 0.3, y: r.minY + r.height * 0.5), control: CGPoint(x: r.minX + r.width * 0.45, y: r.minY + r.height * 0.2))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.minY + r.height * 0.62), control: CGPoint(x: r.minX + r.width * 0.15, y: r.minY + r.height * 0.5))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.maxY), control: CGPoint(x: r.minX + r.width * 0.45, y: r.maxY))
        p.closeSubpath()
        return p
    }
}

/// A small bat wing, drawn for the left side: the shoulder is the bottom-right corner, the bone runs along
/// the top to the tip, and the membrane hangs in two scallops.
private struct DragonWing: View {
    var look: SkinLook

    var body: some View {
        ZStack {
            WingMembrane()
                .fill(LinearGradient(colors: [DragonPalette.membrane, DragonPalette.membraneDark], startPoint: .topLeading, endPoint: .bottomTrailing))
            WingBones()
                .stroke(DragonPalette.limbDark, style: StrokeStyle(lineWidth: look.small ? 2 : 1.6, lineCap: .round, lineJoin: .round))
        }
    }
}

private struct WingMembrane: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let shoulder = CGPoint(x: r.maxX, y: r.maxY)
        let tip = CGPoint(x: r.minX, y: r.minY)
        p.move(to: shoulder)
        p.addQuadCurve(to: tip, control: CGPoint(x: r.midX + r.width * 0.1, y: r.minY - r.height * 0.05))
        p.addQuadCurve(to: CGPoint(x: r.minX + r.width * 0.28, y: r.minY + r.height * 0.72), control: CGPoint(x: r.minX + r.width * 0.02, y: r.minY + r.height * 0.5))
        p.addQuadCurve(to: CGPoint(x: r.minX + r.width * 0.62, y: r.minY + r.height * 0.8), control: CGPoint(x: r.minX + r.width * 0.42, y: r.minY + r.height * 0.6))
        p.addQuadCurve(to: shoulder, control: CGPoint(x: r.minX + r.width * 0.78, y: r.minY + r.height * 0.78))
        p.closeSubpath()
        return p
    }
}

private struct WingBones: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let shoulder = CGPoint(x: r.maxX, y: r.maxY)
        let tip = CGPoint(x: r.minX, y: r.minY)
        p.move(to: shoulder)
        p.addQuadCurve(to: tip, control: CGPoint(x: r.midX + r.width * 0.1, y: r.minY - r.height * 0.05))
        let knuckle = CGPoint(x: r.midX + r.width * 0.05, y: r.minY + r.height * 0.18)
        p.move(to: knuckle)
        p.addLine(to: CGPoint(x: r.minX + r.width * 0.28, y: r.minY + r.height * 0.72))
        p.move(to: knuckle)
        p.addLine(to: CGPoint(x: r.minX + r.width * 0.62, y: r.minY + r.height * 0.8))
        return p
    }
}

/// A tube along a cubic curve (points in unit coordinates of the frame) that narrows from `start` to `end`
/// points wide: a dense chain of circles, so tight bends never fold the outline over itself.
struct TaperedCurve: Shape {
    var points: [CGPoint]
    var start: Double
    var end: Double

    func path(in r: CGRect) -> Path {
        guard points.count == 4 else { return Path() }
        let p = points.map { CGPoint(x: r.minX + $0.x * r.width, y: r.minY + $0.y * r.height) }
        var path = Path()
        let steps = 48
        for i in 0...steps {
            let t = Double(i) / Double(steps), u = 1 - t
            let a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t
            let x = a * p[0].x + b * p[1].x + c * p[2].x + d * p[3].x
            let y = a * p[0].y + b * p[1].y + c * p[2].y + d * p[3].y
            let radius = (start + (end - start) * t) / 2
            path.addEllipse(in: CGRect(x: x - radius, y: y - radius, width: radius * 2, height: radius * 2))
        }
        return path
    }
}

/// The heart-shaped spade at the tail's tip, pointing up.
private struct Spade: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.midX, y: r.minY))
        p.addCurve(to: CGPoint(x: r.midX, y: r.maxY - r.height * 0.18), control1: CGPoint(x: r.maxX + r.width * 0.25, y: r.minY + r.height * 0.55),
                   control2: CGPoint(x: r.maxX - r.width * 0.05, y: r.maxY + r.height * 0.05))
        p.addLine(to: CGPoint(x: r.midX + r.width * 0.08, y: r.maxY))
        p.addLine(to: CGPoint(x: r.midX - r.width * 0.08, y: r.maxY))
        p.addLine(to: CGPoint(x: r.midX, y: r.maxY - r.height * 0.18))
        p.addCurve(to: CGPoint(x: r.midX, y: r.minY), control1: CGPoint(x: r.minX + r.width * 0.05, y: r.maxY + r.height * 0.05),
                   control2: CGPoint(x: r.minX - r.width * 0.25, y: r.minY + r.height * 0.55))
        p.closeSubpath()
        return p
    }
}

/// A small rounded spike.
private struct Spike: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.midX, y: r.minY), control: CGPoint(x: r.minX + r.width * 0.2, y: r.midY))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.maxY), control: CGPoint(x: r.maxX - r.width * 0.2, y: r.midY))
        p.closeSubpath()
        return p
    }
}

/// A flame drop: round at the bottom, pointed at the top.
private struct Flame: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.midX, y: r.minY))
        p.addCurve(to: CGPoint(x: r.midX, y: r.maxY), control1: CGPoint(x: r.maxX + r.width * 0.1, y: r.midY),
                   control2: CGPoint(x: r.maxX, y: r.maxY))
        p.addCurve(to: CGPoint(x: r.midX, y: r.minY), control1: CGPoint(x: r.minX, y: r.maxY),
                   control2: CGPoint(x: r.minX - r.width * 0.1, y: r.midY))
        p.closeSubpath()
        return p
    }
}

/// A small "w" mouth.
private struct MouthW: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.midX, y: r.minY + r.height * 0.2), control: CGPoint(x: r.minX + r.width * 0.25, y: r.minY + r.height * 1.1))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.minY), control: CGPoint(x: r.maxX - r.width * 0.25, y: r.minY + r.height * 1.1))
        return p
    }
}
