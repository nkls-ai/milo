import Combine
import SwiftUI

/// The capsule over Milo that shows his ears and his head: a light the instant the key goes down, a level meter
/// that follows the voice with the words so far, "Got it" when the key comes up, then dots while he works out
/// what was said and thinks. One surface that changes shape, so each step reads as the next one.
struct VoiceCapsule: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var model: MiloModel

    var body: some View {
        if let phase = model.voicePhase {
            let color = Surface.color(for: phase.mode, theme)
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    VoiceIndicator(phase: phase, live: model.live, color: color)
                    if phase == .thinking, let since = model.thinkingSince {
                        // Checks the clock once a second, only while he thinks.
                        TimelineView(.periodic(from: .now, by: 1)) { _ in
                            label(Self.thinkingLabel(after: model.now() - since, words: words(phase) != nil), phase)
                        }
                    } else {
                        label(Self.label(phase, words: words(phase) != nil), phase)
                    }
                    if case .listening(_, handsFree: true) = phase {
                        Image(systemName: "lock.fill")
                            .font(.system(size: 9.5, weight: .bold))
                            .foregroundStyle(color)
                            .accessibilityLabel("Hands-free")
                    }
                }
                if let words = words(phase) {
                    Text(words)
                        .font(.system(size: 12.5))
                        .foregroundStyle(theme.ink.opacity(phase.recording ? 0.95 : 0.6))
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: Surface.textWidth - 24, alignment: .leading)
                        .transition(.opacity)
                }
            }
            .padding(.horizontal, phase.isArmed ? 8 : 12)
            .padding(.vertical, 7)
            .floatingSurface(RoundedRectangle(cornerRadius: Surface.capsuleRadius, style: .continuous),
                             edge: phase.recording ? color.opacity(0.5) : nil)
            .padding(.trailing, Surface.trailingInset)
            .transition(reduceMotion ? .opacity : .asymmetric(
                // No fade in: the light is there in the first frame and only grows.
                insertion: .scale(scale: 0.55, anchor: .bottomTrailing),
                removal: .scale(scale: 0.85, anchor: .bottomTrailing).combined(with: .opacity)))
            .accessibilityElement(children: .combine)
            .accessibilityLabel(phase.spoken)
            .accessibilityValue(words(phase) ?? "")
        }
    }

    @ViewBuilder private func label(_ text: String?, _ phase: VoicePhase) -> some View {
        if let text {
            Text(text)
                .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                .foregroundStyle(theme.ink.opacity(phase == .offline ? 0.6 : 0.9))
                .fixedSize()
                .transition(.opacity)
        }
    }

    /// The words to show under the label: what was heard so far, then what the brain made of it.
    private func words(_ phase: VoicePhase) -> String? {
        switch phase {
        case .listening(_, let handsFree):
            if let partial = model.partial { return Self.tail(partial) }
            return handsFree ? "Tap the key again when you're done. Esc cancels." : nil
        case .caught, .transcribing:
            return model.partial.map { Self.tail($0) }
        case .thinking:
            return model.heard.map { Self.tail("“\($0)”") }
        default:
            return nil
        }
    }

    /// The label next to the indicator. Thinking with the user's words above needs none: the dots say it.
    static func label(_ phase: VoicePhase, words: Bool) -> String? {
        switch phase {
        case .armed: nil
        case .listening(.talk, _): "Listening"
        case .listening(.dictate, _): "Dictating"
        case .caught: "Got it"
        case .transcribing(.dictate): "Writing it down"
        case .transcribing(.talk): words ? nil : "One moment"
        case .pasted: "Pasted"
        case .thinking: words ? nil : "Thinking"
        case .offline: "Waking up"
        }
    }

    /// Thinking for longer than a moment says so, so a slow answer never looks stuck.
    static func thinkingLabel(after seconds: TimeInterval, words: Bool) -> String? {
        switch seconds {
        case ..<6: label(.thinking, words: words)
        case ..<20: "Still on it"
        default: "Taking a while"
        }
    }

    /// The last `limit` characters, cut at a word, so the newest words stay visible.
    static func tail(_ text: String, limit: Int = 140) -> String {
        guard text.count > limit else { return text }
        let end = text.suffix(limit + 1)
        let start = end.firstIndex(of: " ").map { end.index(after: $0) } ?? end.startIndex
        return "…" + end[start...]
    }
}

/// The small picture at the start of the capsule, in a fixed frame so the capsule only grows to the right.
struct VoiceIndicator: View {
    @Environment(\.miloTheme) private var theme
    let phase: VoicePhase
    let live: LiveLevel
    let color: Color

    var body: some View {
        ZStack {
            switch phase {
            case .armed:
                RecordingLight(color: color).transition(.scale(scale: 0.6).combined(with: .opacity))
            case .listening:
                LevelMeter(live: live, color: color).transition(.opacity)
            case .caught, .pasted:
                DoneTick(color: color).transition(.scale(scale: 0.5).combined(with: .opacity))
            case .transcribing, .thinking:
                ThinkingDots(color: color).transition(.opacity)
            case .offline:
                ThinkingDots(color: theme.ink.opacity(0.35)).transition(.opacity)
            }
        }
        .frame(width: phase.isArmed ? 14 : 30, height: 16)
        .accessibilityHidden(true)
    }
}

/// A lit dot, like the light on a camera: the mic is on.
struct RecordingLight: View {
    let color: Color

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 10, height: 10)
            .background(Circle().fill(color.opacity(0.3)).frame(width: 16, height: 16))
    }
}

/// A meter that follows the voice: the newest level in the middle, older ones moving outwards, sampled at a
/// steady pace so silence settles instead of freezing a shape. It reads the level on its own ticks rather than
/// watching it, so only the meter redraws.
struct LevelMeter: View {
    let live: LiveLevel
    let color: Color
    /// Newest first.
    @State private var history = [Double](repeating: 0, count: 4)
    @State private var ticks = Timer.publish(every: 0.05, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 2.5) {
            ForEach(-3...3, id: \.self) { i in
                Capsule()
                    .fill(color.opacity(1 - Double(abs(i)) * 0.14))
                    .frame(width: 2.5, height: 3 + 13 * Self.height(history[abs(i)]))
            }
        }
        .frame(height: 16)
        .animation(.spring(response: 0.16, dampingFraction: 0.75), value: history)
        .onReceive(ticks) { _ in
            history = [live.level] + history.dropLast()
        }
    }

    /// Bar height 0...1 for a mic level: room noise stays flat, a normal voice fills most of it.
    static func height(_ level: Double) -> Double {
        pow(min(1, max(0, (level - 0.04) / 0.7)), 0.7)
    }
}

/// The meter for places that show a fixed level, like the Milo window's "Listening…" row.
struct LevelBars: View {
    var level: Double
    var color: Color
    private let weights: [Double] = [0.5, 0.8, 1.0, 0.75, 0.45]

    var body: some View {
        HStack(spacing: 3) {
            ForEach(weights.indices, id: \.self) { i in
                Capsule()
                    .fill(color)
                    .frame(width: 3.5, height: 5 + 15 * min(1, level * 1.6) * weights[i])
            }
        }
        .frame(height: 20)
        .animation(.easeOut(duration: 0.08), value: level)
    }
}

/// Three dots in a slow wave. Drawn from the clock, so they keep moving however long he thinks and however often
/// the view around them changes. With Reduce Motion they glow in turn instead of moving.
struct ThinkingDots: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var color: Color

    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 4) {
                ForEach(0..<3) { i in
                    let wave = Self.wave(at: t, dot: i)
                    Circle()
                        .fill(color)
                        .frame(width: 6, height: 6)
                        .opacity(reduceMotion ? 0.35 + 0.65 * wave : 0.55 + 0.45 * wave)
                        .offset(y: reduceMotion ? 0 : -3 * wave)
                }
            }
        }
        .frame(height: 16)
    }

    /// 0...1 for dot `dot` at time `t`: each rises a little after the one before, then all rest a moment.
    static func wave(at t: TimeInterval, dot: Int) -> Double {
        let phase = (t / 1.1 - Double(dot) * 0.16).truncatingRemainder(dividingBy: 1)
        return max(0, sin((phase < 0 ? phase + 1 : phase) * 2 * .pi))
    }
}

/// A filled circle whose tick draws itself: done, got it.
struct DoneTick: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let color: Color
    @State private var drawn = false

    var body: some View {
        ZStack {
            Circle().fill(color)
            CheckBadge.Tick()
                .trim(from: 0, to: drawn ? 1 : 0)
                .stroke(theme.onPrimary, style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
                .padding(4.5)
        }
        .frame(width: 16, height: 16)
        .onAppear {
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.22).delay(0.05)) { drawn = true }
        }
    }
}
