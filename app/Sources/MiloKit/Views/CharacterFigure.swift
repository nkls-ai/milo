import SwiftUI

/// What the figure is told: Milo's state and feelings, the life layer's pose and where he is flying.
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

    /// Asleep with his eyes shut, not mid-yawn.
    var sleeping: Bool { shown == .sleepy && !pose.yawn }
}

/// Draws Milo, the wren. The overlay, the helpers, the windows and the setup scenes all use this:
/// `CharacterFigure(for: model.character, size: 36)`.
struct CharacterFigure: View {
    var style: CharacterStyle
    var input: FigureInput
    /// The figure's box in points. He is framed for 120, with his feet near the bottom.
    var size: CGFloat
    /// Fixes the clock, for renders: a still drawing of the pose this input settles into.
    var time: Double?

    init(for style: CharacterStyle = .milo, state: MiloState = .idle, emotion: Emotion = .neutral, asleep: Bool = false,
         level: Double = 0, connected: Bool = true, pose: LifePose = LifePose(), flight: Flight = .perched,
         words: Int = 0, asking: Bool = false, working: Bool = false, size: CGFloat = 120, time: Double? = nil) {
        self.init(for: style, input: FigureInput(state: state, emotion: emotion, asleep: asleep, level: level,
                                                 connected: connected, pose: pose, flight: flight, words: words,
                                                 asking: asking, working: working),
                  size: size, time: time)
    }

    init(for style: CharacterStyle = .milo, input: FigureInput, size: CGFloat = 120, time: Double? = nil) {
        self.style = style
        self.input = input
        self.size = size
        self.time = time
    }

    /// Helper size and smaller: fewer fine lines, a bolder silhouette.
    private var small: Bool { size < 60 }

    var body: some View {
        WrenFigure(input: input, small: small, still: time != nil)
            .overlay { FigureMarks(input: input, small: small, frozen: time != nil, time: time ?? 0).scaleEffect(size / 120) }
            .frame(width: size, height: size)
            .opacity(input.connected ? 1 : 0.55)
            .saturation(input.connected ? 1 : 0.2)
    }
}

/// Floating marks by his head: a rising "z" while asleep, a bobbing "?" when confused, a sparkle when
/// excited. They play on Core Animation's clock, so they cost nothing between changes. Drawn in the
/// 120 pt box; his crown is near (60, 30) and he faces left, so the marks sit behind his head.
struct FigureMarks: View {
    var input: FigureInput
    var small: Bool
    var frozen: Bool
    var time: Double

    static let sleepAt = CGPoint(x: 84, y: 30)
    static let questionAt = CGPoint(x: 86, y: 20)

    var body: some View {
        ZStack {
            switch input.shown {
            case .sleepy where input.sleeping:
                ForEach(0..<2, id: \.self) { i in
                    Looping(Self.rise(phase: Double(i) * 1.3), frozen: frozen, time: time) {
                        Text("z").font(.system(size: i == 0 ? 15 : 11, weight: .bold, design: .rounded))
                            .foregroundStyle(Color(cgColor: WrenColors.bodyMid))
                            .frame(width: 24, height: 24)
                    }
                    .frame(width: 24, height: 24)
                    .position(x: Self.sleepAt.x + Double(i) * 7, y: Self.sleepAt.y - Double(i) * 5)
                }
            case .confused:
                Looping(.float(period: 2, height: 6), frozen: frozen, time: time) {
                    Text("?").font(.system(size: 20, weight: .heavy, design: .rounded))
                        .foregroundStyle(Color(cgColor: WrenColors.scarfLo))
                        .frame(width: 24, height: 28)
                }
                .frame(width: 24, height: 28)
                .position(Self.questionAt)
            case .excited where !small:
                Looping(Loop(period: 1.2, keys: [.init(at: 0, sx: 0.85, sy: 0.85, angle: -10),
                                                 .init(at: 0.5, sx: 1.15, sy: 1.15, angle: 10),
                                                 .init(at: 1, sx: 0.85, sy: 0.85, angle: -10)]),
                        frozen: frozen, time: time) {
                    Image(systemName: "sparkle").font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color(cgColor: WrenColors.scarfHi))
                        .frame(width: 24, height: 24)
                }
                .frame(width: 24, height: 24)
                .position(x: 120 - Self.questionAt.x + 4, y: Self.questionAt.y + 6)
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
