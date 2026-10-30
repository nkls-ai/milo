import SwiftUI

/// The purple robot with the antenna (`[ui] character = "classic"`). He floats; while he points, a small hand
/// shows on the side of the target and the antenna leans that way.
struct RobotFigure: Skin {
    var look: SkinLook

    static func idleLoop(_ look: SkinLook) -> Loop? {
        guard !look.airborne else { return nil }
        return look.sleeping ? .float(period: 6, height: 3) : .float(period: 4.4, height: 6)
    }

    private var stateColor: Color {
        switch look.state {
        case .listening: Palette.talk
        case .dictating: Palette.dictate
        case .transcribing, .thinking: Palette.think
        case .speaking: Palette.speak
        case .idle: look.airborne ? Palette.speak : Palette.idle
        }
    }

    /// The direction he points in, view coordinates, while pointing.
    private var pointing: CGVector? {
        if case let .pointing(toward) = look.flight { toward } else { nil }
    }

    var body: some View {
        ZStack {
            ListeningRing(look: look, center: CGPoint(x: 60, y: 66), diameter: 112)
            GroundShadow(look: look, width: 50, y: 113)
            robot
                .scaleEffect(x: 1 - look.stretch * 0.6, y: 1 + look.stretch, anchor: UnitPoint(x: 0.5, y: 112 / 120))
                .rotationEffect(.degrees(look.tilt), anchor: UnitPoint(x: 0.5, y: 112 / 120))
                .scaleEffect(1 + abs(look.pose.lean) * 0.05, anchor: .bottom)
                .offset(x: look.airborne ? 0 : look.pose.lean * 3, y: look.airborne ? 0 : look.lift * 0.5)
                .animation(.spring(response: 0.2, dampingFraction: 0.45), value: look.pose.squash)
                .animation(.spring(response: 0.45, dampingFraction: 0.7), value: look.pose.lean)
                .animation(.spring(response: 0.3, dampingFraction: 0.55), value: look.pose.tilt)
                .animation(.spring(response: 0.4, dampingFraction: 0.75), value: look.flight)
            Marks(look: look, at: CGPoint(x: 106, y: 22), sleepColor: Palette.bodyTop)
        }
        .frame(width: 120, height: 120)
    }

    private var robot: some View {
        ZStack {
            if let toward = pointing {
                // A floating hand, like the Visor sketch: out from the body toward the target.
                Circle()
                    .fill(LinearGradient(colors: [Palette.bodyTop, Palette.bodyBottom], startPoint: .top, endPoint: .bottom))
                    .frame(width: 15, height: 15)
                    .shadow(color: Palette.bodyBottom.opacity(0.4), radius: 3, y: 2)
                    .position(x: 60 + Double(toward.dx) * 62, y: 70 + Double(toward.dy) * 50)
            }
            Antenna(color: stateColor, active: look.state != .idle || look.airborne, look: look)
                .rotationEffect(.degrees(Double(pointing?.dx ?? 0) * 25 + (look.sleeping ? 14 : 0)), anchor: .bottom)
                .position(x: 60, y: 11)
            ZStack {
                RoundedRectangle(cornerRadius: 44, style: .continuous)
                    .fill(LinearGradient(colors: [Palette.bodyTop, Palette.bodyBottom], startPoint: .top, endPoint: .bottom))
                    .frame(width: 98, height: 88)
                    .shadow(color: Palette.bodyBottom.opacity(look.small ? 0 : 0.45), radius: 10, y: 6)
                Ellipse()
                    .fill(Color.white.opacity(0.28))
                    .frame(width: 34, height: 16)
                    .rotationEffect(.degrees(-24))
                    .offset(x: -24, y: -27)
                Face(emotion: look.pose.yawn ? .sleepy : look.emotion, speaking: look.speaking, level: look.level,
                     blinking: look.pose.blink, gaze: look.gaze, yawning: look.pose.yawn)
                    .offset(x: look.gaze.dx * 2.5, y: 4 + look.gaze.dy * 2)
                    .animation(.spring(response: 0.25, dampingFraction: 0.8), value: look.gaze)
                    .animation(.easeInOut(duration: 0.07), value: look.pose.blink)
            }
            .scaleEffect(x: 1 + look.level * 0.04, y: 1 - look.level * 0.03, anchor: .bottom)
            .animation(.easeOut(duration: 0.08), value: look.level)
            .position(x: 60, y: 68)
        }
        .frame(width: 120, height: 120)
    }
}

/// The robot's antenna: a stalk and a bulb in the colour of what he's doing, glowing while he's busy.
struct Antenna: View {
    var color: Color
    var active: Bool
    var look: SkinLook

    var body: some View {
        VStack(spacing: -1) {
            ZStack {
                if active {
                    Looping(Loop(period: 1.4, keys: [.init(at: 0, sx: 0.8, sy: 0.8, opacity: 0.35),
                                                     .init(at: 0.5, sx: 1.25, sy: 1.25, opacity: 0.9),
                                                     .init(at: 1, sx: 0.8, sy: 0.8, opacity: 0.35)]),
                            frozen: look.frozen, time: look.time) {
                        Circle().fill(color).frame(width: 13, height: 13).blur(radius: 4).frame(width: 30, height: 30)
                    }
                    .frame(width: 30, height: 30)
                }
                Circle()
                    .fill(color)
                    .frame(width: 13, height: 13)
                    .shadow(color: color.opacity(0.4), radius: 3)
            }
            .frame(width: 30, height: 13)
            Capsule()
                .fill(Palette.bodyTop)
                .frame(width: 4, height: 12)
        }
        .frame(height: 26)
    }
}
