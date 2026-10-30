import SwiftUI

struct CharacterView: View {
    @ObservedObject var model: MiloModel
    @StateObject private var life = CharacterLifeDriver()

    private var asleep: Bool { model.drowsy && model.state == .idle && model.bubble == nil }

    var body: some View {
        CharacterFigure(state: model.state, emotion: model.emotion, asleep: asleep, level: model.level,
                        connected: model.connected, pose: life.pose, floating: life.onScreen)
            .background(LifeAnchor(driver: life))
            .onAppear {
                life.start()
                life.update(state: model.state, asleep: asleep)
            }
            .onDisappear { life.stop() }
            .onChange(of: model.state) { life.update(state: model.state, asleep: asleep) }
            .onChange(of: asleep) { life.update(state: model.state, asleep: asleep) }
    }
}

/// The drawing, given everything it shows. No timers of its own except the float, so it renders offscreen too.
struct CharacterFigure: View {
    var state: MiloState
    var emotion: Emotion
    var asleep: Bool
    var level: Double
    var connected: Bool
    var pose: LifePose
    /// Pauses the float while the window is hidden.
    var floating = true
    @State private var pulse = false

    private var shown: Emotion {
        if asleep && !pose.hovered { return .sleepy }
        if pose.pleased && emotion == .neutral && state == .idle { return .happy }
        return emotion
    }

    private var stateColor: Color {
        switch state {
        case .listening: Palette.talk
        case .dictating: Palette.dictate
        case .transcribing, .thinking: Palette.think
        case .speaking: Palette.speak
        case .idle: Palette.idle
        }
    }

    var body: some View {
        // The float moves 3 pt over seconds, so 15 updates a second look smooth and cost a fraction
        // of a repeatForever animation, which redraws at the display's full rate.
        TimelineView(.animation(minimumInterval: 1.0 / 15, paused: !floating)) { context in
            figure(time: context.date.timeIntervalSinceReferenceDate)
        }
        .opacity(connected ? 1 : 0.55)
        .saturation(connected ? 1 : 0.2)
    }

    private func figure(time: Double) -> some View {
        let sleeping = shown == .sleepy
        let float = sin(time * 2 * .pi / (sleeping ? 6 : 4.4)) * (sleeping ? 1.5 : 3)
        return ZStack {
            if state == .listening || state == .dictating {
                Circle()
                    .stroke(stateColor.opacity(0.55), lineWidth: 3)
                    .frame(width: 118, height: 118)
                    .scaleEffect(pulse ? 1.12 + level * 0.2 : 0.95)
                    .opacity(pulse ? 0.25 : 0.9)
                    .animation(.easeOut(duration: 0.9).repeatForever(autoreverses: false), value: pulse)
                    .onAppear { pulse = true }
                    .onDisappear { pulse = false }
            }
            Antenna(color: stateColor, active: state != .idle)
                .offset(y: -58)
            ZStack {
                RoundedRectangle(cornerRadius: 44, style: .continuous)
                    .fill(LinearGradient(colors: [Palette.bodyTop, Palette.bodyBottom], startPoint: .top, endPoint: .bottom))
                    .frame(width: 104, height: 96)
                    .shadow(color: Palette.bodyBottom.opacity(0.45), radius: 10, y: 6)
                Ellipse()
                    .fill(Color.white.opacity(0.28))
                    .frame(width: 34, height: 16)
                    .rotationEffect(.degrees(-24))
                    .offset(x: -26, y: -30)
                Face(emotion: pose.yawn ? .sleepy : shown, speaking: state == .speaking, level: level,
                     blinking: pose.blink, gaze: pose.gaze, yawning: pose.yawn)
                    .offset(x: pose.gaze.dx * 2.5, y: 4 + pose.gaze.dy * 2)
                    .animation(.spring(response: 0.25, dampingFraction: 0.8), value: pose.gaze)
                    .animation(.easeInOut(duration: 0.07), value: pose.blink)
            }
            .scaleEffect(x: 1 + level * 0.04, y: 1 - level * 0.03, anchor: .bottom)
            .animation(.easeOut(duration: 0.08), value: level)
            Extras(emotion: shown, time: time)
        }
        .scaleEffect(x: 1 - pose.squash * 0.6, y: 1 + pose.squash, anchor: .bottom)
        .animation(.spring(response: 0.2, dampingFraction: 0.45), value: pose.squash)
        .rotationEffect(.degrees(pose.lean * 6 + pose.tilt), anchor: .bottom)
        .scaleEffect(1 + abs(pose.lean) * 0.05, anchor: .bottom)
        .offset(x: pose.lean * 3)
        .animation(.spring(response: 0.45, dampingFraction: 0.7), value: pose.lean)
        .animation(.spring(response: 0.3, dampingFraction: 0.55), value: pose.tilt)
        .offset(y: float)
    }
}

struct Antenna: View {
    var color: Color
    var active: Bool
    @State private var glow = false

    var body: some View {
        VStack(spacing: -1) {
            Circle()
                .fill(color)
                .frame(width: 13, height: 13)
                .shadow(color: color.opacity(active ? 0.9 : 0.4), radius: glow && active ? 9 : 3)
                .animation(.easeInOut(duration: 0.7).repeatForever(), value: glow)
            Capsule()
                .fill(Palette.bodyTop)
                .frame(width: 4, height: 14)
        }
        .onAppear { glow = true }
    }
}

/// Floating marks around the head, moved by the figure's clock instead of their own animations.
struct Extras: View {
    var emotion: Emotion
    var time: Double

    var body: some View {
        ZStack {
            switch emotion {
            case .sleepy:
                let rise = (time / 2.4).truncatingRemainder(dividingBy: 1)
                Text("z").font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundStyle(Palette.idle)
                    .offset(x: 52 + rise * 6, y: -48 - rise * 12)
                    .opacity(1 - rise)
            case .confused:
                Text("?").font(.system(size: 20, weight: .heavy, design: .rounded))
                    .foregroundStyle(Palette.think)
                    .offset(x: 50, y: -44 + sin(time * .pi) * 3)
            case .excited:
                Image(systemName: "sparkle").font(.system(size: 16, weight: .bold))
                    .foregroundStyle(Palette.think)
                    .offset(x: -52, y: -40)
                    .scaleEffect(1 + 0.15 * sin(time * 2 * .pi / 1.2))
            default:
                EmptyView()
            }
        }
    }
}
