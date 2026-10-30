import SwiftUI

enum PipPalette {
    static let bodyLight = Color(red: 0.70, green: 0.66, blue: 0.92)
    static let bodyDark = Color(red: 0.42, green: 0.36, blue: 0.75)
    static let wing = Color(red: 0.40, green: 0.34, blue: 0.70)
    static let wingDark = Color(red: 0.32, green: 0.27, blue: 0.60)
    static let crest = Color(red: 0.52, green: 0.46, blue: 0.82)
    static let bellyLight = Color(red: 0.99, green: 0.91, blue: 0.82)
    static let bellyDark = Color(red: 0.95, green: 0.75, blue: 0.58)
    static let beak = Color(red: 0.96, green: 0.66, blue: 0.27)
    static let beakDark = Color(red: 0.84, green: 0.52, blue: 0.18)
    static let mouth = Color(red: 0.42, green: 0.20, blue: 0.22)
    static let feet = Color(red: 0.86, green: 0.58, blue: 0.27)
    static let eye = Color(red: 0.13, green: 0.10, blue: 0.24)
    static let eyeRing = Color(red: 0.86, green: 0.83, blue: 0.97)
    static let cheek = Color(red: 0.95, green: 0.58, blue: 0.64)
}

/// Pip, the small lavender bird. Drawn in a 120 pt box with his body centred at (60, 66) and his feet on
/// y = 107. Same inputs as `CharacterFigure` plus the flight. One clock drives breathing and the tuft:
/// 15 Hz while he sits, faster only while he flies, paused while hidden.
struct PipFigure: View {
    var state: MiloState
    var emotion: Emotion
    var asleep: Bool
    var level: Double
    var connected: Bool
    var pose: LifePose
    var flight: Flight = .perched
    var floating = true
    /// Fixes the clock, for renders.
    var time: Double?
    @State private var hops = 0

    private var shown: Emotion {
        if asleep && !pose.hovered { return .sleepy }
        if pose.pleased && emotion == .neutral && state == .idle { return .happy }
        return emotion
    }

    var body: some View {
        Group {
            if let time {
                bird(time: time)
            } else {
                TimelineView(.animation(minimumInterval: flight.airborne ? 1.0 / 40 : 1.0 / 15, paused: !floating)) {
                    bird(time: $0.date.timeIntervalSinceReferenceDate)
                }
            }
        }
        .frame(width: 120, height: 120)
        .opacity(connected ? 1 : 0.55)
        .saturation(connected ? 1 : 0.2)
        .onChange(of: shown) { old, new in
            if (new == .happy || new == .excited) && old != .happy && old != .excited { hops += 1 }
        }
    }

    private func bird(time: Double) -> some View {
        let look = PipLook(state: state, emotion: shown, level: level, pose: pose, flight: flight, time: time)
        return ZStack {
            if state == .listening || state == .dictating {
                ListeningRing(color: state == .listening ? Palette.talk : Palette.dictate, level: level)
            }
            Ellipse()
                .fill(Color.black.opacity(look.airborne ? 0 : 0.16))
                .frame(width: 46, height: 6)
                .blur(radius: 2)
                .position(x: 60, y: 108.5)
            PipBody(look: look)
                .keyframeAnimator(initialValue: 0.0, trigger: hops) { content, lift in
                    content.offset(y: lift)
                } keyframes: { _ in
                    KeyframeTrack {
                        SpringKeyframe(-9, duration: 0.17, spring: .snappy)
                        SpringKeyframe(0, duration: 0.2, spring: .bouncy)
                        SpringKeyframe(-3.5, duration: 0.12, spring: .snappy)
                        SpringKeyframe(0, duration: 0.2, spring: .smooth)
                    }
                }
            Extras(emotion: shown, time: time, sleepColor: PipPalette.crest)
                .offset(x: -2, y: 8)
        }
    }
}

/// Everything about Pip's pose at one moment, worked out once so the parts stay simple.
struct PipLook {
    var state: MiloState
    var emotion: Emotion
    var level: Double
    var pose: LifePose
    var flight: Flight
    var time: Double

    var airborne: Bool { flight.airborne }
    var sleeping: Bool { emotion == .sleepy && !pose.yawn }
    var speaking: Bool { state == .speaking }

    /// Eyes and beak follow the gaze a little further than the eyes alone, which reads as a turned head.
    var gaze: CGVector {
        switch flight {
        case let .pointing(toward): CGVector(dx: toward.dx * 0.8, dy: toward.dy * 0.8)
        case let .flying(heading): CGVector(dx: heading.dx * 0.6, dy: heading.dy * 0.3)
        case .perched: sleeping ? .zero : pose.gaze
        }
    }

    var breath: Double {
        let period = sleeping ? 5.5 : 3.6
        return sin(time * 2 * .pi / period) * (sleeping ? 0.022 : 0.012)
    }

    /// Degrees, clockwise. Leaning toward the user while listening, a slow sway while thinking.
    var tilt: Double {
        switch flight {
        case let .flying(heading): return heading.dx * 12
        case let .pointing(toward): return toward.dx * 5
        case .perched: break
        }
        var degrees = pose.lean * 6 + pose.tilt
        if state == .thinking || state == .transcribing { degrees += sin(time * 2 * .pi / 2.8) * 3 }
        if emotion == .confused { degrees -= 8 }
        if emotion == .concerned { degrees -= 3 }
        if sleeping { degrees += 4 }
        return degrees
    }

    /// Vertical squash and stretch: positive is taller.
    var stretch: Double {
        var s = pose.squash
        if sleeping { s -= 0.06 }
        if emotion == .sad { s -= 0.035 }
        if speaking { s -= level * 0.025 }
        return s
    }

    /// Points up; a stretch lifts him off his feet a little, which reads as a hop.
    var lift: Double {
        if airborne { return 0 }
        return -max(0, pose.squash) * 55 + (sleeping ? 3 : 0) + (emotion == .sad ? 2 : 0)
    }

    /// How open the beak is, 0...1.
    var beakOpen: Double {
        if pose.yawn { return 1 }
        if speaking { return min(1, level * 1.1) }
        if emotion == .excited { return 0.3 }
        return 0
    }

    /// Rotations of the three tuft feathers in degrees, and how tall they stand.
    var crest: (angles: [Double], scale: Double) {
        var angles = [-24.0, -5, 15]
        var scale = 1.0
        switch emotion {
        case .sleepy where !pose.yawn:
            angles = angles.map { $0 + 48 }
            scale = 0.8
        case .sad:
            angles = [-50, -20, 40]
            scale = 0.82
        case .happy, .excited:
            angles = [-30, -6, 22]
            scale = 1.12
        case .confused:
            angles = [-38, 8, 34]
        default:
            break
        }
        if state == .thinking || state == .transcribing {
            // Ruffles: each feather on its own slow beat.
            for i in angles.indices {
                let beat = 0.9 + Double(i) * 0.23
                angles[i] += sin(time * 2 * .pi / beat + Double(i)) * 9
            }
            scale *= 1.06
        }
        if state == .listening || state == .dictating { scale *= 1.08 + level * 0.25 }
        if airborne { angles = angles.map { $0 + 22 } }
        return (angles, scale)
    }

    /// Wing rotations in degrees around the shoulder (clockwise), and the length of each.
    var wings: (left: Double, right: Double, leftLength: Double, rightLength: Double) {
        var left = -9.0, right = 9.0
        var leftLength = 1.0, rightLength = 1.0
        switch flight {
        case .flying:
            let beat = 0.5 + 0.5 * sin(time * 2 * .pi * 4.2)
            left = 25 + beat * 70
            right = -left
        case let .pointing(toward):
            let angle = atan2(-toward.dx, toward.dy) * 180 / .pi
            let nudge = sin(time * 2 * .pi / 1.6) * 3
            if toward.dx <= 0 {
                left = angle + nudge
                leftLength = 1.14
            } else {
                right = angle - 360 * (angle > 0 ? 1 : 0) + nudge
                rightLength = 1.14
            }
        case .perched:
            if sleeping {
                left = -6
                right = 6
            } else if emotion == .happy || emotion == .excited {
                left = 16
                right = -16
            } else if pose.squash > 0.06 {
                left = 10
                right = -10
            }
            if emotion == .excited { let flutter = sin(time * 2 * .pi * 3) * 8; left += flutter; right -= flutter }
            if emotion == .concerned || emotion == .sad { left -= 4; right += 4 }
        }
        return (left, right, leftLength, rightLength)
    }
}

/// The bird without his shadow: tail, feet, body, wings, tuft and face.
private struct PipBody: View {
    var look: PipLook

    var body: some View {
        let gaze = look.gaze
        let wings = look.wings
        let crest = look.crest
        ZStack {
            Tail()
                .fill(PipPalette.wingDark)
                .frame(width: 19, height: 15)
                .rotationEffect(.degrees(look.airborne ? 0 : 28), anchor: .leading)
                .position(x: 90, y: 93)
            Feet()
                .stroke(PipPalette.feet, style: StrokeStyle(lineWidth: 2.4, lineCap: .round, lineJoin: .round))
                .frame(width: 34, height: 10)
                .position(x: 60, y: 102)
                .opacity(look.airborne || look.sleeping ? 0 : 1)
            ForEach(0..<3, id: \.self) { i in
                Feather()
                    .fill(PipPalette.crest)
                    .frame(width: [6.0, 7.5, 6.0][i], height: [15.0, 19, 13][i] * crest.scale)
                    .rotationEffect(.degrees(crest.angles[i]), anchor: .bottom)
                    .position(x: 56 + Double(i) * 4.5 + gaze.dx * 1.5,
                              y: 37 - [15.0, 19, 13][i] * crest.scale / 2)
            }
            torso
            Wing()
                .fill(LinearGradient(colors: [PipPalette.wing, PipPalette.wingDark], startPoint: .top, endPoint: .bottom))
                .overlay(WingFeathers().stroke(PipPalette.bodyLight.opacity(0.25), style: StrokeStyle(lineWidth: 1, lineCap: .round)))
                .frame(width: 16, height: 33 * wings.leftLength)
                .rotationEffect(.degrees(wings.left), anchor: .top)
                .position(x: 29.5, y: 59 + 33 * wings.leftLength / 2)
            Wing()
                .fill(LinearGradient(colors: [PipPalette.wing, PipPalette.wingDark], startPoint: .top, endPoint: .bottom))
                .overlay(WingFeathers().stroke(PipPalette.bodyLight.opacity(0.25), style: StrokeStyle(lineWidth: 1, lineCap: .round)))
                .frame(width: 16, height: 33 * wings.rightLength)
                .scaleEffect(x: -1)
                .rotationEffect(.degrees(wings.right), anchor: .top)
                .position(x: 90.5, y: 59 + 33 * wings.rightLength / 2)
            PipFace(look: look)
                .offset(x: gaze.dx * 3.2 + (look.sleeping ? 5 : 0), y: gaze.dy * 2.2 + (look.sleeping ? 4 : 0))
        }
        .frame(width: 120, height: 120)
        .scaleEffect(x: 1 - look.stretch * 0.6, y: 1 + look.stretch, anchor: UnitPoint(x: 0.5, y: 107 / 120))
        .rotationEffect(.degrees(look.tilt), anchor: UnitPoint(x: 0.5, y: 107 / 120))
        .offset(x: look.airborne ? 0 : look.pose.lean * 3, y: look.lift)
        .animation(.spring(response: 0.22, dampingFraction: 0.5), value: look.pose.squash)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.pose.lean)
        .animation(.spring(response: 0.3, dampingFraction: 0.6), value: look.pose.tilt)
        .animation(.spring(response: 0.25, dampingFraction: 0.8), value: look.pose.gaze)
        .animation(.spring(response: 0.4, dampingFraction: 0.75), value: look.emotion)
        .animation(.spring(response: 0.4, dampingFraction: 0.75), value: look.state)
        .animation(.easeOut(duration: 0.08), value: look.level)
    }

    /// Body and belly. They breathe; the feet and wings stay put.
    private var torso: some View {
        ZStack {
            Egg()
                .fill(RadialGradient(colors: [PipPalette.bodyLight, PipPalette.bodyDark],
                                     center: UnitPoint(x: 0.36, y: 0.26), startRadius: 4, endRadius: 70))
            Ellipse()
                .fill(LinearGradient(colors: [PipPalette.bellyLight, PipPalette.bellyDark], startPoint: .top, endPoint: .bottom))
                .frame(width: 46, height: 38)
                .position(x: 38, y: 60)
            BellyMarks()
                .stroke(PipPalette.bellyDark.opacity(0.7), style: StrokeStyle(lineWidth: 1.1, lineCap: .round))
                .frame(width: 18, height: 9)
                .position(x: 38, y: 62)
            Ellipse()
                .fill(Color.white.opacity(0.24))
                .frame(width: 18, height: 8)
                .rotationEffect(.degrees(-28))
                .blur(radius: 1.2)
                .position(x: 21, y: 15)
        }
        .frame(width: 76, height: 72)
        .clipShape(Egg())
        .shadow(color: PipPalette.bodyDark.opacity(0.35), radius: 6, y: 4)
        .scaleEffect(x: 1 + look.breath * 0.5 + look.level * 0.02 * (look.speaking ? 1 : 0), y: 1 + look.breath,
                     anchor: .bottom)
        .position(x: 60, y: 66)
    }
}

private struct PipFace: View {
    var look: PipLook

    var body: some View {
        let emotion = look.emotion
        let eyeShift = CGSize(width: look.gaze.dx * 2.2, height: look.gaze.dy * 1.8)
        ZStack {
            ForEach([true, false], id: \.self) { left in
                Ellipse()
                    .fill(PipPalette.cheek.opacity(emotion == .happy || emotion == .excited ? 0.62 : 0.4))
                    .frame(width: 9, height: 5)
                    .blur(radius: 0.7)
                    .position(x: left ? 42.5 : 77.5, y: 69)
                PipEye(look: look, left: left)
                    .offset(eyeShift)
                    .position(x: left ? 47 : 73, y: 60)
                PipBrow(emotion: emotion, left: left)
                    .position(x: left ? 46 : 74, y: 51.5)
            }
            PipBeak(open: look.beakOpen, sleeping: look.sleeping)
                .position(x: 60, y: 68.5)
        }
        .frame(width: 120, height: 120)
    }
}

private struct PipEye: View {
    var look: PipLook
    var left: Bool

    var body: some View {
        let emotion = look.emotion
        ZStack {
            if look.pose.yawn || emotion == .sleepy {
                ArcShape(up: false)
                    .stroke(PipPalette.eye, style: StrokeStyle(lineWidth: 2.4, lineCap: .round))
                    .frame(width: 9, height: 2.5)
            } else if emotion == .happy {
                ArcShape(up: true)
                    .stroke(PipPalette.eye, style: StrokeStyle(lineWidth: 2.6, lineCap: .round))
                    .frame(width: 9.5, height: 4)
                    .offset(y: 1)
            } else {
                let size = eyeSize
                Ellipse()
                    .fill(PipPalette.eye)
                    .frame(width: size.width, height: look.pose.blink ? 1.6 : size.height)
                    .overlay(alignment: .topTrailing) {
                        Circle().fill(.white).frame(width: size.width * 0.36)
                            .offset(x: -size.width * 0.14, y: size.height * 0.14)
                            .opacity(look.pose.blink ? 0 : 1)
                    }
                    .offset(y: emotion == .sad ? 1 : 0)
                if emotion == .excited && !look.pose.blink {
                    Circle().fill(.white.opacity(0.85)).frame(width: 1.8).offset(x: -1.8, y: 2.2)
                }
            }
        }
        .frame(width: 16, height: 16)
        .animation(.easeInOut(duration: 0.07), value: look.pose.blink)
    }

    private var eyeSize: CGSize {
        switch look.emotion {
        case .excited: CGSize(width: 10.5, height: 11.5)
        case .confused: left ? CGSize(width: 9.5, height: 10.5) : CGSize(width: 6.5, height: 7)
        case .sad, .concerned: CGSize(width: 8, height: 8)
        default: CGSize(width: 8.6, height: 9.6)
        }
    }
}

/// Pale feathers over the eyes. Hidden until an emotion needs them.
private struct PipBrow: View {
    var emotion: Emotion
    var left: Bool

    var body: some View {
        let tilt: Double = switch emotion {
        case .concerned, .sad: left ? -20 : 20
        case .confused: left ? -6 : 14
        case .thinking: left ? 8 : -8
        default: 0
        }
        Capsule()
            .fill(PipPalette.eyeRing)
            .frame(width: 10, height: 2.6)
            .rotationEffect(.degrees(tilt))
            .offset(y: emotion == .thinking ? -1.5 : 0)
            .opacity([.concerned, .sad, .confused, .thinking].contains(emotion) ? 0.95 : 0)
    }
}

private struct PipBeak: View {
    var open: Double
    var sleeping: Bool

    var body: some View {
        ZStack(alignment: .top) {
            Ellipse()
                .fill(PipPalette.mouth)
                .frame(width: 8, height: 1 + open * 8)
                .offset(y: 3)
                .opacity(open > 0.05 ? 1 : 0)
            BeakHalf(upper: false)
                .fill(PipPalette.beakDark)
                .frame(width: 9.5, height: 5)
                .offset(y: 2.5 + open * 6)
            BeakHalf(upper: true)
                .fill(LinearGradient(colors: [PipPalette.beak, PipPalette.beakDark], startPoint: .top, endPoint: .bottom))
                .frame(width: 12.5, height: 6.5)
                .offset(y: -1.5)
        }
        .frame(width: 14, height: 16, alignment: .top)
        .scaleEffect(sleeping ? 0.8 : 1)
        .rotationEffect(.degrees(sleeping ? 14 : 0))
    }
}

/// The soft ring behind Pip while he records, in the colour of the mode.
private struct ListeningRing: View {
    var color: Color
    var level: Double
    @State private var pulse = false

    var body: some View {
        Circle()
            .stroke(color.opacity(0.5), lineWidth: 2.5)
            .frame(width: 104, height: 104)
            .scaleEffect(pulse ? 1.1 + level * 0.18 : 0.94)
            .opacity(pulse ? 0.2 : 0.85)
            .animation(.easeOut(duration: 0.9).repeatForever(autoreverses: false), value: pulse)
            .position(x: 60, y: 64)
            .onAppear { pulse = true }
            .onDisappear { pulse = false }
    }
}

// MARK: Shapes

/// A body that sits: a little narrower at the head, widest just below the middle.
struct Egg: Shape {
    func path(in r: CGRect) -> Path {
        let w = r.width, h = r.height, x = r.minX, y = r.minY
        let side = y + h * 0.56
        var p = Path()
        p.move(to: CGPoint(x: x + w / 2, y: y))
        p.addCurve(to: CGPoint(x: x + w, y: side), control1: CGPoint(x: x + w * 0.80, y: y),
                   control2: CGPoint(x: x + w, y: y + h * 0.24))
        p.addCurve(to: CGPoint(x: x + w / 2, y: y + h), control1: CGPoint(x: x + w, y: y + h * 0.85),
                   control2: CGPoint(x: x + w * 0.79, y: y + h))
        p.addCurve(to: CGPoint(x: x, y: side), control1: CGPoint(x: x + w * 0.21, y: y + h),
                   control2: CGPoint(x: x, y: y + h * 0.85))
        p.addCurve(to: CGPoint(x: x + w / 2, y: y), control1: CGPoint(x: x, y: y + h * 0.24),
                   control2: CGPoint(x: x + w * 0.20, y: y))
        p.closeSubpath()
        return p
    }
}

/// A folded wing: round at the shoulder (top), tapering to a tip at the bottom, with the outer edge
/// fuller than the inner one. Drawn for the left side; mirror it for the right.
struct Wing: Shape {
    func path(in r: CGRect) -> Path {
        let w = r.width, h = r.height, x = r.minX, y = r.minY
        var p = Path()
        p.move(to: CGPoint(x: x + w * 0.55, y: y))
        p.addCurve(to: CGPoint(x: x + w, y: y + h * 0.4), control1: CGPoint(x: x + w * 0.9, y: y),
                   control2: CGPoint(x: x + w, y: y + h * 0.18))
        p.addCurve(to: CGPoint(x: x + w * 0.62, y: y + h), control1: CGPoint(x: x + w, y: y + h * 0.68),
                   control2: CGPoint(x: x + w * 0.8, y: y + h * 0.9))
        p.addCurve(to: CGPoint(x: x, y: y + h * 0.42), control1: CGPoint(x: x + w * 0.3, y: y + h * 0.86),
                   control2: CGPoint(x: x, y: y + h * 0.66))
        p.addCurve(to: CGPoint(x: x + w * 0.55, y: y), control1: CGPoint(x: x, y: y + h * 0.16),
                   control2: CGPoint(x: x + w * 0.24, y: y))
        p.closeSubpath()
        return p
    }
}

/// Two faint lines toward the wing tip, where the long flight feathers lie.
private struct WingFeathers: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        for (start, end) in [(0.52, 0.86), (0.6, 0.78)] {
            let x = r.minX + r.width * (start == 0.52 ? 0.62 : 0.4)
            p.move(to: CGPoint(x: x, y: r.minY + r.height * start))
            p.addQuadCurve(to: CGPoint(x: r.minX + r.width * 0.6, y: r.minY + r.height * end),
                           control: CGPoint(x: x + r.width * 0.08, y: r.minY + r.height * (start + end) / 2))
        }
        return p
    }
}

/// One tuft feather, anchored at its base (bottom).
struct Feather: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.midX, y: r.maxY))
        p.addCurve(to: CGPoint(x: r.midX + r.width * 0.15, y: r.minY), control1: CGPoint(x: r.maxX + r.width * 0.2, y: r.maxY - r.height * 0.35),
                   control2: CGPoint(x: r.maxX, y: r.minY + r.height * 0.2))
        p.addCurve(to: CGPoint(x: r.midX, y: r.maxY), control1: CGPoint(x: r.minX, y: r.minY + r.height * 0.3),
                   control2: CGPoint(x: r.minX - r.width * 0.1, y: r.maxY - r.height * 0.3))
        p.closeSubpath()
        return p
    }
}

/// A short tail fan behind the body: narrow where it meets him, spreading into two rounded feathers.
private struct Tail: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.midY - r.height * 0.18))
        p.addLine(to: CGPoint(x: r.maxX - r.width * 0.12, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.maxX - r.width * 0.06, y: r.midY), control: CGPoint(x: r.maxX + 1, y: r.minY + r.height * 0.2))
        p.addQuadCurve(to: CGPoint(x: r.maxX - r.width * 0.2, y: r.maxY), control: CGPoint(x: r.maxX, y: r.maxY - r.height * 0.1))
        p.addLine(to: CGPoint(x: r.minX, y: r.midY + r.height * 0.18))
        p.closeSubpath()
        return p
    }
}

/// Two legs, each with three short toes.
private struct Feet: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        for cx in [r.minX + r.width * 0.26, r.maxX - r.width * 0.26] {
            p.move(to: CGPoint(x: cx, y: r.minY))
            p.addLine(to: CGPoint(x: cx, y: r.maxY - 1))
            p.move(to: CGPoint(x: cx - 4.5, y: r.maxY))
            p.addLine(to: CGPoint(x: cx + 4.5, y: r.maxY))
            p.move(to: CGPoint(x: cx, y: r.maxY - 1))
            p.addLine(to: CGPoint(x: cx + 1.5, y: r.maxY))
        }
        return p
    }
}

/// Three faint feather scallops on the chest.
private struct BellyMarks: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let marks: [(CGFloat, CGFloat)] = [(0.2, 0.2), (0.62, 0.05), (0.42, 0.75)]
        for (fx, fy) in marks {
            let c = CGPoint(x: r.minX + r.width * fx, y: r.minY + r.height * fy)
            p.move(to: CGPoint(x: c.x - 3, y: c.y))
            p.addQuadCurve(to: CGPoint(x: c.x + 3, y: c.y), control: CGPoint(x: c.x, y: c.y + 3))
        }
        return p
    }
}

/// The upper half points down to a tip; the lower half is a smaller wedge under it.
private struct BeakHalf: Shape {
    var upper: Bool
    func path(in r: CGRect) -> Path {
        var p = Path()
        if upper {
            p.move(to: CGPoint(x: r.minX, y: r.minY + r.height * 0.25))
            p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.minY + r.height * 0.25), control: CGPoint(x: r.midX, y: r.minY - r.height * 0.25))
            p.addQuadCurve(to: CGPoint(x: r.midX, y: r.maxY), control: CGPoint(x: r.maxX - r.width * 0.12, y: r.maxY * 0.75 + r.minY * 0.25))
            p.addQuadCurve(to: CGPoint(x: r.minX, y: r.minY + r.height * 0.25), control: CGPoint(x: r.minX + r.width * 0.12, y: r.maxY * 0.75 + r.minY * 0.25))
        } else {
            p.move(to: CGPoint(x: r.minX, y: r.minY))
            p.addLine(to: CGPoint(x: r.maxX, y: r.minY))
            p.addQuadCurve(to: CGPoint(x: r.minX, y: r.minY), control: CGPoint(x: r.midX, y: r.maxY + r.height * 0.6))
        }
        p.closeSubpath()
        return p
    }
}
