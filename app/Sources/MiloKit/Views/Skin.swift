import SwiftUI

/// What any figure is told: Milo's state and feelings, the life layer's pose and where he is flying.
struct FigureInput: Equatable {
    var state: MiloState = .idle
    var emotion: Emotion = .neutral
    /// Drowsy, idle and quiet: he sleeps unless the cursor is on him.
    var asleep = false
    /// Mic or voice loudness, 0...1.
    var level = 0.0
    var connected = true
    var pose = LifePose()
    var flight: Flight = .perched
    /// Words heard so far in the recording in progress. Each new one may earn a small nod.
    var words = 0
    /// A yes-or-no question is waiting on the user.
    var asking = false
    /// He is working in a window (perched on it) or driving the mouse and keys.
    var working = false

    /// The feeling the face shows: sleepy while asleep, a smile while the cursor first arrives.
    var shown: Emotion {
        if asleep && !pose.hovered { return .sleepy }
        if pose.pleased && emotion == .neutral && state == .idle { return .happy }
        return emotion
    }
}

/// Everything a skin draws from at one moment, worked out once so every skin reads it the same way.
/// Skins draw in a 120 pt box with the feet (or the bottom of the body) on y = 107.
struct SkinLook: Equatable {
    var state: MiloState
    /// What the face shows (`FigureInput.shown`).
    var emotion: Emotion
    var level: Double
    var pose: LifePose
    var flight: Flight
    /// Seconds. Only changes between frames while a skin asks for a frame rate, or in renders.
    var time: Double
    /// Renders: Core Animation can't run, so `Looping` draws the pose at `time` instead.
    var frozen: Bool
    /// 0 to 1 and back while a nod plays.
    var nod = 0.0
    /// Drawn at helper size (around 36 pt): skip hairlines and fine marks.
    var small = false

    var airborne: Bool { flight.airborne }
    var sleeping: Bool { emotion == .sleepy && !pose.yawn }
    var speaking: Bool { state == .speaking }
    var listening: Bool { state == .listening || state == .dictating }
    var thinking: Bool { state == .thinking || state == .transcribing }
    var happy: Bool { emotion == .happy || emotion == .excited }

    /// Where the head looks, each axis -1...1, x right, y down: at the target while pointing, ahead while
    /// flying, straight out while asleep, else the life layer's gaze, dipped by a nod.
    var gaze: CGVector {
        switch flight {
        case let .pointing(toward): return CGVector(dx: toward.dx * 0.8, dy: toward.dy * 0.8)
        case let .flying(heading): return CGVector(dx: heading.dx * 0.6, dy: heading.dy * 0.3)
        case .perched:
            if sleeping { return .zero }
            return CGVector(dx: pose.gaze.dx, dy: min(1, pose.gaze.dy + nod * 0.5))
        }
    }

    /// -1 when the user (the middle of the screen) is to the left, 1 to the right; from the lean while listening.
    var side: Double { pose.lean > 0 ? 1 : -1 }

    /// How open the mouth or beak is, 0...1.
    var mouthOpen: Double {
        if pose.yawn { return 1 }
        if speaking { return min(1, level * 1.1) }
        if emotion == .excited { return 0.3 }
        return 0
    }

    /// The head tilt every skin shares, in degrees clockwise: toward the target or the flight, leaning in
    /// while listening, a quizzical tilt when confused.
    var tilt: Double {
        switch flight {
        case let .flying(heading): return heading.dx * 12
        case let .pointing(toward): return toward.dx * 5
        case .perched: break
        }
        var degrees = pose.lean * 6 + pose.tilt
        if emotion == .confused { degrees -= 8 }
        if emotion == .concerned { degrees -= 3 }
        if sleeping { degrees += 4 }
        return degrees
    }

    /// Vertical squash and stretch, positive is taller: the life layer's bounces, sinking when sad or asleep,
    /// a dip on each nod.
    var stretch: Double {
        var s = pose.squash
        if sleeping { s -= 0.06 }
        if emotion == .sad { s -= 0.035 }
        if speaking { s -= level * 0.025 }
        return s - nod * 0.035
    }

    /// Points up; a stretch lifts him off his feet a little, which reads as a hop.
    var lift: Double {
        if airborne { return 0 }
        return -max(0, pose.squash) * 55 + (sleeping ? 3 : 0) + (emotion == .sad ? 2 : 0)
    }
}

/// A way Milo can look. A skin is a view of one `SkinLook`; the stage around it adds the clock, the slow
/// idle loop, the hop when he's pleased and the nods while you talk, so every skin gets them for free.
protocol Skin: View {
    init(look: SkinLook)
    /// Frames a second the skin must be redrawn at for this look, or nil when it holds still between pose
    /// changes. Prefer `Looping` for anything that repeats: it costs nothing while Milo sits there.
    static func frameRate(_ look: SkinLook) -> Double?
    /// The motion the whole body repeats, e.g. breathing. Nil holds still.
    static func idleLoop(_ look: SkinLook) -> Loop?
}

extension Skin {
    static func frameRate(_ look: SkinLook) -> Double? { nil }
}

/// Draws Milo in any skin. Track 4's helpers and the Settings previews use this too:
/// `CharacterFigure(for: model.character, size: 36)`.
struct CharacterFigure: View {
    var style: CharacterStyle
    var input: FigureInput
    /// The figure's box in points. The skins are drawn for 120.
    var size: CGFloat
    /// Fixes the clock, for renders: loops show their pose at this time and nothing animates.
    var time: Double?

    init(for style: CharacterStyle, state: MiloState = .idle, emotion: Emotion = .neutral, asleep: Bool = false,
         level: Double = 0, connected: Bool = true, pose: LifePose = LifePose(), flight: Flight = .perched,
         words: Int = 0, size: CGFloat = 120, time: Double? = nil) {
        self.init(for: style, input: FigureInput(state: state, emotion: emotion, asleep: asleep, level: level,
                                                 connected: connected, pose: pose, flight: flight, words: words),
                  size: size, time: time)
    }

    init(for style: CharacterStyle, input: FigureInput, size: CGFloat = 120, time: Double? = nil) {
        self.style = style
        self.input = input
        self.size = size
        self.time = time
    }

    var body: some View {
        switch style {
        case .pip: FigureStage<PipFigure>(input: input, size: size, time: time)
        case .classic: FigureStage<RobotFigure>(input: input, size: size, time: time)
        case .dragon: FigureStage<DragonFigure>(input: input, size: size, time: time)
        case .kit: FigureStage<KitFigure>(input: input, size: size, time: time)
        case .glow: FigureStage<GlowFigure>(input: input, size: size, time: time)
        }
    }
}

/// Runs one skin: the clock (only when the skin asks for one), the idle loop, hops and nods, the dimming
/// while the brain is away. Scales the 120 pt drawing to `size`.
struct FigureStage<S: Skin>: View {
    var input: FigureInput
    var size: CGFloat
    var time: Double?
    @State private var hops = 0
    @State private var nods = 0
    @State private var lastNod = Date.distantPast

    /// A nod at most this often, so a fast talker doesn't make him bob like a toy.
    static var nodGap: TimeInterval { 0.7 }

    var body: some View {
        Group {
            if let time {
                stage(time: time, frozen: true)
            } else if let rate = S.frameRate(look(time: 0, frozen: false, nod: 0)) {
                TimelineView(.animation(minimumInterval: 1 / rate)) { context in
                    stage(time: context.date.timeIntervalSinceReferenceDate, frozen: false)
                }
            } else {
                stage(time: 0, frozen: false)
            }
        }
        .frame(width: size, height: size)
        .opacity(input.connected ? 1 : 0.55)
        .saturation(input.connected ? 1 : 0.2)
        .onChange(of: input.shown) { old, new in
            let glad: Set<Emotion> = [.happy, .excited]
            if glad.contains(new) && !glad.contains(old) { hops += 1 }
        }
        .onChange(of: input.words) { old, new in
            guard new > old, input.state == .listening || input.state == .dictating,
                  Date().timeIntervalSince(lastNod) > Self.nodGap else { return }
            lastNod = Date()
            nods += 1
        }
    }

    private func look(time: Double, frozen: Bool, nod: Double) -> SkinLook {
        SkinLook(state: input.state, emotion: input.shown, level: input.level, pose: input.pose, flight: input.flight,
                 time: time, frozen: frozen, nod: nod, small: size < 60)
    }

    private func stage(time: Double, frozen: Bool) -> some View {
        let scale = size / 120
        return KeyframeAnimator(initialValue: 0.0, trigger: nods) { nod in
            let look = look(time: time, frozen: frozen, nod: nod)
            Looping(S.idleLoop(look)?.scaled(by: scale), frozen: frozen, time: time) {
                S(look: look)
                    .frame(width: 120, height: 120)
                    .scaleEffect(scale)
                    .frame(width: size, height: size)
            }
            .frame(width: size, height: size)
        } keyframes: { _ in
            KeyframeTrack {
                SpringKeyframe(1, duration: 0.14, spring: .snappy)
                SpringKeyframe(0, duration: 0.3, spring: .smooth)
            }
        }
        .keyframeAnimator(initialValue: 0.0, trigger: hops) { content, lift in
            content.offset(y: lift * scale)
        } keyframes: { _ in
            KeyframeTrack {
                SpringKeyframe(-9, duration: 0.17, spring: .snappy)
                SpringKeyframe(0, duration: 0.2, spring: .bouncy)
                SpringKeyframe(-3.5, duration: 0.12, spring: .snappy)
                SpringKeyframe(0, duration: 0.2, spring: .smooth)
            }
        }
    }
}

extension Loop {
    /// The same loop for a figure drawn `factor` times its 120 pt size.
    func scaled(by factor: Double) -> Loop {
        var loop = self
        loop.keys = keys.map { var k = $0; k.dx *= factor; k.dy *= factor; return k }
        return loop
    }
}

/// Floating marks near the head: a rising "z" while asleep, a bobbing "?" when confused, a sparkle when
/// excited. `at` is the spot just above and beside the head, in the skin's 120 pt box.
struct Marks: View {
    var look: SkinLook
    var at: CGPoint
    var sleepColor = Palette.idle
    var color = Palette.think

    var body: some View {
        ZStack {
            switch look.emotion {
            case .sleepy where !look.pose.yawn:
                ForEach(0..<2, id: \.self) { i in
                    Looping(Self.rise(phase: Double(i) * 1.3), frozen: look.frozen, time: look.time) {
                        Text("z").font(.system(size: i == 0 ? 15 : 11, weight: .bold, design: .rounded))
                            .foregroundStyle(sleepColor)
                            .frame(width: 24, height: 24)
                    }
                    .frame(width: 24, height: 24)
                    .position(x: at.x + Double(i) * 7, y: at.y - Double(i) * 5)
                }
            case .confused:
                Looping(.float(period: 2, height: 6), frozen: look.frozen, time: look.time) {
                    Text("?").font(.system(size: 20, weight: .heavy, design: .rounded))
                        .foregroundStyle(color)
                        .frame(width: 24, height: 28)
                }
                .frame(width: 24, height: 28)
                .position(at)
            case .excited where !look.small:
                Looping(Loop(period: 1.2, keys: [.init(at: 0, sx: 0.85, sy: 0.85, angle: -10),
                                                 .init(at: 0.5, sx: 1.15, sy: 1.15, angle: 10),
                                                 .init(at: 1, sx: 0.85, sy: 0.85, angle: -10)]),
                        frozen: look.frozen, time: look.time) {
                    Image(systemName: "sparkle").font(.system(size: 16, weight: .bold))
                        .foregroundStyle(color)
                        .frame(width: 24, height: 24)
                }
                .frame(width: 24, height: 24)
                .position(x: 120 - at.x, y: at.y + 4)
            default:
                EmptyView()
            }
        }
        .frame(width: 120, height: 120)
        .allowsHitTesting(false)
    }

    /// A "z" drifting up and away while it fades.
    static func rise(phase: Double) -> Loop {
        Loop(period: 2.6, keys: [.init(at: 0, dx: -2, dy: 4, sx: 0.7, sy: 0.7, opacity: 0),
                                 .init(at: 0.25, dx: 0, dy: 0, opacity: 1),
                                 .init(at: 1, dx: 7, dy: -14, sx: 1.1, sy: 1.1, opacity: 0)],
             smooth: false, phase: phase)
    }
}

/// A soft ring behind the figure while it records, in the colour of the mode, pulsing outward.
struct ListeningRing: View {
    var look: SkinLook
    var center = CGPoint(x: 60, y: 64)
    var diameter = 104.0

    var body: some View {
        if look.listening {
            let color = look.state == .listening ? Palette.talk : Palette.dictate
            Looping(Loop(period: 0.9, keys: [.init(at: 0, sx: 0.94, sy: 0.94, opacity: 0.85),
                                             .init(at: 1, sx: 1.12, sy: 1.12, opacity: 0.15)], smooth: false),
                    frozen: look.frozen, time: look.time) {
                Circle()
                    .stroke(color.opacity(0.5), lineWidth: 2.5)
                    .frame(width: diameter, height: diameter)
                    .scaleEffect(1 + look.level * 0.12)
                    .frame(width: diameter * 1.4, height: diameter * 1.4)
            }
            .frame(width: diameter * 1.4, height: diameter * 1.4)
            .position(center)
        }
    }
}

/// The soft shadow under a figure that sits; gone while it flies.
struct GroundShadow: View {
    var look: SkinLook
    var width = 46.0
    var y = 108.5

    var body: some View {
        Ellipse()
            .fill(Color.black.opacity(look.airborne ? 0 : 0.16))
            .frame(width: width, height: 6)
            .blur(radius: look.small ? 0 : 2)
            .position(x: 60, y: y)
    }
}
