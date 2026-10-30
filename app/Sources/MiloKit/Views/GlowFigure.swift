import SwiftUI

enum GlowPalette {
    static let halo = Color(red: 1.0, green: 0.82, blue: 0.48)
    static let haloEdge = Color(red: 1.0, green: 0.70, blue: 0.28)
    static let core = Color(red: 1.0, green: 0.97, blue: 0.86)
    static let mid = Color(red: 1.0, green: 0.85, blue: 0.56)
    static let rim = Color(red: 0.95, green: 0.64, blue: 0.28)
    static let ember = Color(red: 0.86, green: 0.50, blue: 0.27)
    static let emberDark = Color(red: 0.62, green: 0.33, blue: 0.20)
    static let wing = Color(red: 0.93, green: 0.96, blue: 1.0)
    static let vein = Color(red: 0.72, green: 0.80, blue: 0.92)
    static let stalk = Color(red: 0.54, green: 0.42, blue: 0.29)
    static let bulb = Color(red: 1.0, green: 0.85, blue: 0.56)
    static let ink = Color(red: 0.29, green: 0.20, blue: 0.15)
    static let mouth = Color(red: 0.42, green: 0.27, blue: 0.19)
    static let cheek = Color(red: 1.0, green: 0.62, blue: 0.48)
}

/// Glow, a small warm light with paper-thin wings, between a firefly and a lantern. He hovers, glows brighter
/// while you talk, dims to an ember at night, and points by shining a beam on the thing he means.
struct GlowFigure: Skin {
    var look: SkinLook

    static func idleLoop(_ look: SkinLook) -> Loop? {
        guard !look.airborne else { return nil }
        return look.sleeping ? .float(period: 6, height: 2.5) : .float(period: 3.6, height: 5)
    }

    var body: some View {
        ZStack {
            GroundShadow(look: look, width: look.sleeping ? 26 : 32, y: 108)
            if case let .pointing(toward) = look.flight {
                Beam(look: look, toward: toward)
            }
            ListeningRing(look: look, center: CGPoint(x: 60, y: 66), diameter: 100)
            GlowBody(look: look)
            Marks(look: look, at: CGPoint(x: 96, y: 28), sleepColor: GlowPalette.rim, color: GlowPalette.rim)
        }
        .frame(width: 120, height: 120)
    }
}

/// How bright he is, 0...1: low as an ember, full while you talk to him or he answers.
private func glowLevel(_ look: SkinLook) -> Double {
    if look.sleeping { return 0.12 }
    if look.listening { return 0.75 + look.level * 0.25 }
    if look.speaking { return 0.65 + look.level * 0.35 }
    if look.emotion == .excited { return 0.95 }
    if look.happy { return 0.8 }
    if look.emotion == .sad { return 0.4 }
    if look.airborne { return 0.8 }
    return 0.6
}

private struct GlowBody: View {
    var look: SkinLook

    private var asleep: Bool { look.sleeping }

    var body: some View {
        let light = glowLevel(look)
        ZStack {
            halo(light)
            if case let .flying(heading) = look.flight {
                Trail(heading: heading)
            }
            antenna(left: true)
            antenna(left: false)
            wing(left: true)
            wing(left: false)
            orb
            GlowFace(look: look)
                .offset(x: look.gaze.dx * 3, y: look.gaze.dy * 2.2)
        }
        .frame(width: 120, height: 120)
        .scaleEffect(x: 1 - look.stretch * 0.6, y: 1 + look.stretch, anchor: UnitPoint(x: 0.5, y: 93 / 120))
        .rotationEffect(.degrees(look.tilt), anchor: UnitPoint(x: 0.5, y: 66 / 120))
        .offset(x: look.airborne ? 0 : look.pose.lean * 3, y: look.lift * 0.6 + (asleep ? 6 : 0))
        .animation(.spring(response: 0.22, dampingFraction: 0.5), value: look.pose.squash)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.pose.lean)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: look.pose.tilt)
        .animation(.spring(response: 0.25, dampingFraction: 0.8), value: look.pose.gaze)
        .animation(.easeInOut(duration: 0.6), value: look.emotion)
        .animation(.spring(response: 0.4, dampingFraction: 0.75), value: look.state)
        .animation(.easeOut(duration: 0.12), value: look.level)
    }

    /// The soft light around him. It breathes slowly; while he thinks it pulses like an ember.
    private func halo(_ light: Double) -> some View {
        let loop: Loop = look.thinking
            ? Loop(period: 1.8, keys: [.init(at: 0, sx: 0.96, sy: 0.96, opacity: 0.75), .init(at: 0.5, sx: 1.08, sy: 1.08, opacity: 1),
                                       .init(at: 1, sx: 0.96, sy: 0.96, opacity: 0.75)])
            : Loop(period: asleep ? 5.5 : 3.6, keys: [.init(at: 0, sx: 0.97, sy: 0.97, opacity: 0.85),
                                                     .init(at: 0.5, sx: 1.03, sy: 1.03, opacity: 1),
                                                     .init(at: 1, sx: 0.97, sy: 0.97, opacity: 0.85)])
        return Looping(look.small ? nil : loop, frozen: look.frozen, time: look.time) {
            Circle()
                .fill(RadialGradient(colors: [GlowPalette.halo.opacity(0.95), GlowPalette.halo.opacity(0.55),
                                              GlowPalette.haloEdge.opacity(0.18), GlowPalette.haloEdge.opacity(0)],
                                     center: .center, startRadius: 0, endRadius: 54))
                .frame(width: 108, height: 108)
                .scaleEffect(0.82 + light * 0.22)
                .opacity(light)
                .frame(width: 120, height: 120)
        }
        .frame(width: 120, height: 120)
        .position(x: 60, y: 66)
    }

    /// The round light itself. Asleep it cools to a dim ember.
    private var orb: some View {
        ZStack {
            Circle()
                .fill(RadialGradient(colors: [GlowPalette.core, GlowPalette.mid, GlowPalette.rim],
                                     center: UnitPoint(x: 0.4, y: 0.34), startRadius: 1, endRadius: 30))
            Circle()
                .fill(RadialGradient(colors: [GlowPalette.ember, GlowPalette.emberDark],
                                     center: UnitPoint(x: 0.4, y: 0.34), startRadius: 1, endRadius: 30))
                .opacity(asleep ? 0.55 : 0)
            Ellipse()
                .fill(Color.white.opacity(asleep ? 0.25 : 0.6))
                .frame(width: 14, height: 8)
                .rotationEffect(.degrees(-25))
                .offset(x: -10, y: -13)
        }
        .frame(width: 54, height: 54)
        .shadow(color: GlowPalette.haloEdge.opacity(asleep || look.small ? 0 : 0.5), radius: 6)
        .position(x: 60, y: 66)
    }

    /// Two thin feelers with a light at each tip: they lean toward you while you talk and droop at night.
    private func antenna(left: Bool) -> some View {
        let sign = left ? -1.0 : 1.0
        let angle: Double = asleep ? 30 * -sign : (look.listening ? 12 * look.side : (look.emotion == .sad ? 14 * -sign : 0))
        let base = UnitPoint(x: (left ? 55 : 65) / 120, y: 42 / 120)
        return ZStack {
            Feeler()
                .stroke(GlowPalette.stalk, style: StrokeStyle(lineWidth: look.small ? 2.4 : 1.8, lineCap: .round))
                .frame(width: 11, height: 15)
                .scaleEffect(x: left ? 1 : -1)
                .position(x: left ? 49.5 : 70.5, y: 34.5)
            Circle()
                .fill(GlowPalette.bulb)
                .frame(width: 5.4, height: 5.4)
                .shadow(color: GlowPalette.haloEdge.opacity(asleep ? 0 : 0.7), radius: 2)
                .position(x: left ? 44 : 76, y: 27)
        }
        .frame(width: 120, height: 120)
        .rotationEffect(.degrees(angle), anchor: base)
    }

    /// Paper-thin wings behind the light. They buzz while he flies and fold down while he sleeps.
    private func wing(left: Bool) -> some View {
        let sign = left ? -1.0 : 1.0
        let root = UnitPoint(x: (left ? 50 : 70) / 120, y: 54 / 120)
        let fold: Double = asleep ? 36 * -sign : (look.happy ? -10 * -sign : 0)
        let loop: Loop? = switch look.flight {
        case .flying: Loop(period: 0.12, keys: [.init(at: 0), .init(at: 0.5, sx: 1, sy: 0.5, angle: 6 * sign), .init(at: 1)], pivot: root)
        case .pointing: Loop(period: 0.3, keys: [.init(at: 0), .init(at: 0.5, sy: 0.8, angle: 4 * sign), .init(at: 1)], pivot: root)
        case .perched: look.emotion == .excited
            ? Loop(period: 0.2, keys: [.init(at: 0), .init(at: 0.5, sy: 0.8), .init(at: 1)], pivot: root) : nil
        }
        return Looping(loop, frozen: look.frozen, time: look.time) {
            ZStack {
                // A long forewing and a smaller hindwing, both thin enough to see the light through.
                ForEach(0..<2, id: \.self) { i in
                    let size = i == 0 ? CGSize(width: 32, height: 14) : CGSize(width: 22, height: 11)
                    Ellipse()
                        .fill(LinearGradient(colors: [GlowPalette.wing.opacity(0.75), GlowPalette.wing.opacity(0.4)],
                                             startPoint: left ? .trailing : .leading, endPoint: left ? .leading : .trailing))
                        .overlay(WingVeins().stroke(GlowPalette.vein.opacity(look.small || i == 1 ? 0 : 0.7), lineWidth: 0.6)
                                    .scaleEffect(x: left ? -1 : 1))
                        .overlay(Ellipse().stroke(Color.white.opacity(0.7), lineWidth: 0.7))
                        .frame(width: size.width, height: size.height)
                        .rotationEffect(.degrees((i == 0 ? 24 : -8) * sign))
                        .position(x: 60 + sign * (i == 0 ? 24 : 22), y: i == 0 ? 47 : 58)
                }
            }
            .frame(width: 120, height: 120)
        }
        .frame(width: 120, height: 120)
        .rotationEffect(.degrees(fold), anchor: root)
    }
}

private struct GlowFace: View {
    var look: SkinLook

    var body: some View {
        let emotion = look.emotion
        ZStack {
            ForEach([true, false], id: \.self) { left in
                Ellipse()
                    .fill(GlowPalette.cheek.opacity(look.happy ? 0.7 : 0.5))
                    .frame(width: 8, height: 4.6)
                    .position(x: left ? 45 : 75, y: 74)
                GlowEye(look: look, left: left)
                    .position(x: left ? 51 : 69, y: 66)
                if [.concerned, .sad, .confused, .thinking].contains(emotion) {
                    Capsule()
                        .fill(GlowPalette.ink.opacity(0.7))
                        .frame(width: 7, height: 1.8)
                        .rotationEffect(.degrees(browTilt(left: left)))
                        .position(x: left ? 50 : 70, y: 59)
                }
            }
            GlowMouth(look: look)
                .position(x: 60, y: 76)
        }
        .frame(width: 120, height: 120)
    }

    private func browTilt(left: Bool) -> Double {
        switch look.emotion {
        case .concerned, .sad: left ? -18 : 18
        case .confused: left ? -4 : 14
        default: left ? 8 : -8
        }
    }
}

private struct GlowEye: View {
    var look: SkinLook
    var left: Bool

    var body: some View {
        let emotion = look.emotion
        ZStack {
            if look.pose.yawn || emotion == .sleepy {
                ArcShape(up: false)
                    .stroke(GlowPalette.ink, style: StrokeStyle(lineWidth: 2.1, lineCap: .round))
                    .frame(width: 7.5, height: 2.2)
            } else if emotion == .happy {
                ArcShape(up: true)
                    .stroke(GlowPalette.ink, style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                    .frame(width: 7.5, height: 3.4)
                    .offset(y: 1)
            } else {
                let d = diameter
                Ellipse()
                    .fill(GlowPalette.ink)
                    .frame(width: d, height: look.pose.blink ? 1.3 : d * 1.06)
                    .overlay(alignment: .topTrailing) {
                        Circle().fill(.white).frame(width: d * 0.34)
                            .offset(x: -d * 0.16, y: d * 0.14)
                            .opacity(look.pose.blink ? 0 : 1)
                    }
            }
        }
        .frame(width: 12, height: 12)
        .animation(.easeInOut(duration: 0.07), value: look.pose.blink)
    }

    private var diameter: Double {
        switch look.emotion {
        case .excited: 7.8
        case .confused: left ? 7.2 : 5
        case .sad, .concerned: 5.6
        default: look.listening ? 7.0 : 6.4
        }
    }
}

private struct GlowMouth: View {
    var look: SkinLook

    var body: some View {
        let open = look.mouthOpen
        Group {
            if open > 0.05 {
                Ellipse().fill(GlowPalette.mouth).frame(width: 6 + open * 2, height: 2.4 + open * 6)
            } else {
                switch look.emotion {
                case .happy, .excited:
                    SmileShape().fill(GlowPalette.mouth).frame(width: 8, height: 4)
                case .sad, .concerned:
                    ArcShape(up: true)
                        .stroke(GlowPalette.mouth, style: StrokeStyle(lineWidth: 1.6, lineCap: .round))
                        .frame(width: 6, height: 2).offset(y: 1)
                case .confused:
                    WavyShape()
                        .stroke(GlowPalette.mouth, style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                        .frame(width: 7, height: 2.5)
                case .sleepy:
                    Circle().fill(GlowPalette.mouth.opacity(0.7)).frame(width: 2.6, height: 2.6)
                default:
                    Capsule().fill(GlowPalette.mouth).frame(width: 6, height: 2.4)
                }
            }
        }
        .frame(width: 14, height: 12)
        .animation(.easeOut(duration: 0.07), value: open)
    }
}

/// A cone of warm light from him to what he points at, with a soft spot where it lands.
private struct Beam: View {
    var look: SkinLook
    var toward: CGVector

    var body: some View {
        let angle = atan2(Double(toward.dy), Double(toward.dx)) * 180 / .pi
        ZStack {
            BeamCone()
                .fill(LinearGradient(colors: [GlowPalette.halo.opacity(0.7), GlowPalette.halo.opacity(0.06)],
                                     startPoint: .leading, endPoint: .trailing))
                .frame(width: 70, height: 34)
                .offset(x: 35 + 22)
            Ellipse()
                .fill(RadialGradient(colors: [GlowPalette.halo.opacity(0.6), GlowPalette.halo.opacity(0)],
                                     center: .center, startRadius: 0, endRadius: 14))
                .frame(width: 18, height: 28)
                .offset(x: 22 + 68)
        }
        .frame(width: 120, height: 120)
        .rotationEffect(.degrees(angle), anchor: UnitPoint(x: 0.5, y: 66 / 120))
        .offset(y: 6)
        .allowsHitTesting(false)
    }
}

/// A short trail of fading lights behind him while he flies.
private struct Trail: View {
    var heading: CGVector

    var body: some View {
        ZStack {
            ForEach(0..<3, id: \.self) { i in
                let distance = 30.0 + Double(i) * 11
                Circle()
                    .fill(GlowPalette.halo.opacity(0.7 - Double(i) * 0.2))
                    .frame(width: 8 - Double(i) * 2, height: 8 - Double(i) * 2)
                    .position(x: 60 - Double(heading.dx) * distance, y: 66 - Double(heading.dy) * distance)
            }
        }
        .frame(width: 120, height: 120)
    }
}

/// A cone widening to the right: narrow where it leaves him.
private struct BeamCone: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.midY - r.height * 0.12))
        p.addLine(to: CGPoint(x: r.maxX, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.maxY), control: CGPoint(x: r.maxX + r.width * 0.12, y: r.midY))
        p.addLine(to: CGPoint(x: r.minX, y: r.midY + r.height * 0.12))
        p.closeSubpath()
        return p
    }
}

/// One feeler: from its base at the bottom right up and out to the tip at the top left.
private struct Feeler: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.maxX, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.minY), control: CGPoint(x: r.maxX - r.width * 0.25, y: r.minY + r.height * 0.1))
        return p
    }
}

/// Faint veins across a wing.
private struct WingVeins: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX + r.width * 0.1, y: r.midY))
        p.addQuadCurve(to: CGPoint(x: r.maxX - r.width * 0.08, y: r.midY), control: CGPoint(x: r.midX, y: r.midY - r.height * 0.12))
        p.move(to: CGPoint(x: r.midX, y: r.midY - r.height * 0.04))
        p.addLine(to: CGPoint(x: r.midX + r.width * 0.2, y: r.minY + r.height * 0.15))
        p.move(to: CGPoint(x: r.midX - r.width * 0.12, y: r.midY))
        p.addLine(to: CGPoint(x: r.midX + r.width * 0.05, y: r.maxY - r.height * 0.12))
        return p
    }
}
