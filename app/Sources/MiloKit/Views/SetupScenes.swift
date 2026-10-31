import SwiftUI

/// Little looping scenes in the setup window that show what Milo does with each permission, drawn with the
/// wren himself. They play only while the window is open; with Reduce Motion each shows its telling moment still.
struct PermissionScene: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let permission: Permission?
    /// Play the loop. Off when the window is closed, and in offscreen renders.
    let playing: Bool
    /// The step shown while not playing: the last, where the scene makes its point.
    var still = 2
    /// The key on the last step's key cap.
    var key = "fn"

    static let size = CGSize(width: 148, height: 100)

    var body: some View {
        Group {
            if playing && !reduceMotion {
                PhaseAnimator([0, 1, 2]) { step in
                    scene(step)
                } animation: { step in
                    // Hold each step a beat; the reset back to the start is calmer.
                    step == 0 ? theme.motion.gentle.delay(1.2) : theme.motion.spring.delay(0.55)
                }
            } else {
                scene(still)
            }
        }
        .frame(width: Self.size.width, height: Self.size.height)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(theme.tint))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .accessibilityHidden(true)
    }

    @ViewBuilder private func scene(_ step: Int) -> some View {
        ZStack(alignment: .topLeading) {
            switch permission {
            case .microphone: HearScene(step: step)
            case .accessibility: PressScene(step: step)
            case .screenRecording: PeekScene(step: step)
            case .calendars: PinScene(step: step)
            case .reminders: TickScene(step: step)
            case .automation: DraftScene(step: step)
            case nil: TryScene(step: step, key: key)
            }
        }
        .frame(width: Self.size.width, height: Self.size.height, alignment: .topLeading)
    }
}

/// Milo himself in a scene, small, at `at` (his centre).
private struct Actor: View {
    @Environment(\.miloTheme) private var theme
    var state: MiloState = .idle
    var emotion: Emotion = .neutral
    var gaze = CGVector.zero
    var size: CGFloat = 50
    var at: CGPoint

    var body: some View {
        CharacterFigure(state: state, emotion: emotion, pose: LifePose(gaze: gaze), size: size)
            .frame(width: size, height: size)
            .position(at)
    }
}

/// A word bubble that pops in: what Milo heard, typed or wrote.
private struct WordChip: View {
    @Environment(\.miloTheme) private var theme
    let text: String
    let shown: Bool
    let at: CGPoint

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(theme.onPrimary)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Capsule().fill(theme.primary))
            .scaleEffect(shown ? 1 : 0.3, anchor: .bottomLeading)
            .opacity(shown ? 1 : 0)
            .position(at)
    }
}

/// Microphone: sound comes in, his ear perks up, the waves turn into words.
private struct HearScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int

    var body: some View {
        Actor(state: step >= 1 ? .listening : .idle, emotion: step == 2 ? .happy : .neutral,
              gaze: CGVector(dx: 0.5, dy: 0), at: CGPoint(x: 40, y: 62))
        ForEach(0..<3) { i in
            Wave()
                .stroke(theme.primary.opacity(0.85 - Double(i) * 0.22), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                .frame(width: 12 + CGFloat(i) * 9, height: 22 + CGFloat(i) * 12)
                .position(x: 86 + CGFloat(i) * 9 + (step == 0 ? 14 : 0), y: 60)
                .opacity(step == 1 ? 1 : 0)
        }
        WordChip(text: "Hi Milo!", shown: step == 2, at: CGPoint(x: 102, y: 30))
        Image(systemName: "waveform")
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(theme.accent)
            .position(x: 128, y: 84)
            .opacity(step == 2 ? 0 : 0.8)
    }

    /// A ")" arc, the classic sign for sound.
    struct Wave: Shape {
        func path(in rect: CGRect) -> Path {
            var p = Path()
            p.move(to: CGPoint(x: rect.maxX, y: rect.minY))
            p.addQuadCurve(to: CGPoint(x: rect.maxX, y: rect.maxY), control: CGPoint(x: rect.minX - rect.width * 0.4, y: rect.midY))
            return p
        }
    }
}

/// A tiny window on the right, as in every scene that happens "on your Mac".
private struct MiniWindow<Content: View>: View {
    @Environment(\.miloTheme) private var theme
    let frame: CGRect
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 3) {
                ForEach(0..<3) { _ in Circle().fill(theme.ink.opacity(0.18)).frame(width: 4.5, height: 4.5) }
            }
            content
        }
        .padding(7)
        .frame(width: frame.width, height: frame.height, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(theme.ink.opacity(0.14), lineWidth: 1))
        .shadow(color: theme.primary.opacity(0.12), radius: 4, y: 2)
        .position(x: frame.midX, y: frame.midY)
    }
}

private struct Lines: View {
    @Environment(\.miloTheme) private var theme
    let widths: [CGFloat]
    var shown = Int.max

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(widths.indices, id: \.self) { i in
                Capsule()
                    .fill(theme.ink.opacity(0.16))
                    .frame(width: i < shown ? widths[i] : 0, height: 3.5)
            }
        }
    }
}

/// Accessibility: Milo's little cursor flies to a button in a window and presses it; his words appear.
private struct PressScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int

    var body: some View {
        MiniWindow(frame: CGRect(x: 62, y: 18, width: 78, height: 66)) {
            Text(step == 2 ? "Dear Anna," : " ")
                .font(.system(size: 9, weight: .medium, design: .rounded))
                .foregroundStyle(theme.ink)
                .frame(height: 10)
            Lines(widths: [52, 38])
            Spacer(minLength: 0)
            HStack {
                Spacer()
                Text("OK")
                    .font(.system(size: 8.5, weight: .bold, design: .rounded))
                    .foregroundStyle(step == 2 ? theme.onPrimary : theme.primary)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(theme.primary.opacity(step == 2 ? 1 : 0.18)))
                    .scaleEffect(step == 2 ? 0.92 : 1)
            }
        }
        Actor(emotion: step == 2 ? .happy : .neutral, gaze: CGVector(dx: 0.6, dy: step == 0 ? -0.3 : 0.1), size: 44,
              at: CGPoint(x: 30, y: 70))
        Pointer()
            .fill(theme.primary)
            .overlay(Pointer().stroke(theme.card, lineWidth: 1.2))
            .frame(width: 13, height: 17)
            .scaleEffect(step == 2 ? 0.85 : 1)
            .position(step == 0 ? CGPoint(x: 42, y: 26) : CGPoint(x: 127, y: 77))
    }

    /// Milo's arrow cursor.
    struct Pointer: Shape {
        func path(in r: CGRect) -> Path {
            var p = Path()
            p.move(to: CGPoint(x: r.minX, y: r.minY))
            p.addLine(to: CGPoint(x: r.minX, y: r.maxY * 0.82))
            p.addLine(to: CGPoint(x: r.width * 0.3, y: r.height * 0.64))
            p.addLine(to: CGPoint(x: r.width * 0.52, y: r.maxY))
            p.addLine(to: CGPoint(x: r.width * 0.68, y: r.height * 0.92))
            p.addLine(to: CGPoint(x: r.width * 0.46, y: r.height * 0.58))
            p.addLine(to: CGPoint(x: r.maxX, y: r.height * 0.58))
            p.closeSubpath()
            return p
        }
    }
}

/// Screen Recording: Milo peeks at a little screen through a magnifying glass.
private struct PeekScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int

    private var lens: CGPoint {
        [CGPoint(x: 84, y: 30), CGPoint(x: 98, y: 44), CGPoint(x: 116, y: 34)][step]
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 3).fill(theme.ink.opacity(0.25)).frame(width: 16, height: 9).position(x: 102, y: 78)
            MiniWindow(frame: CGRect(x: 64, y: 16, width: 76, height: 56)) {
                HStack(alignment: .top, spacing: 6) {
                    RoundedRectangle(cornerRadius: 3).fill(theme.accent.opacity(0.35)).frame(width: 18, height: 16)
                    Lines(widths: [30, 22, 34])
                }
            }
        }
        Actor(emotion: step == 2 ? .happy : .neutral, gaze: CGVector(dx: 0.7, dy: -0.2), size: 44, at: CGPoint(x: 30, y: 70))
        ZStack {
            Capsule().fill(theme.ink.opacity(0.7)).frame(width: 4, height: 13).rotationEffect(.degrees(-45)).offset(x: 13, y: 13)
            Circle().fill(theme.glow.opacity(0.28))
            Circle().strokeBorder(theme.primary, lineWidth: 3)
        }
        .frame(width: 26, height: 26)
        .scaleEffect(step == 2 ? 1.12 : 1)
        .position(lens)
        Text("?")
            .font(.system(size: 13, weight: .heavy, design: .rounded))
            .foregroundStyle(theme.accent)
            .position(x: 50, y: 36)
            .opacity(step == 1 ? 1 : 0)
    }
}

/// Calendars: Milo pins a sticky note onto a little calendar.
private struct PinScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int

    var body: some View {
        VStack(spacing: 0) {
            Rectangle().fill(theme.accent.opacity(0.8)).frame(height: 13)
            Grid(horizontalSpacing: 5, verticalSpacing: 5) {
                ForEach(0..<3) { _ in
                    GridRow { ForEach(0..<4) { _ in RoundedRectangle(cornerRadius: 2).fill(theme.ink.opacity(0.12)).frame(width: 9, height: 8) } }
                }
            }
            .padding(7)
        }
        .frame(width: 70, height: 60)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(theme.card))
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(theme.ink.opacity(0.14), lineWidth: 1))
        .position(x: 104, y: 54)
        Actor(emotion: step == 2 ? .happy : .neutral, gaze: CGVector(dx: 0.6, dy: -0.2), size: 44, at: CGPoint(x: 30, y: 70))
        ZStack(alignment: .top) {
            RoundedRectangle(cornerRadius: 2).fill(theme.glow).frame(width: 24, height: 22)
                .shadow(color: theme.ink.opacity(0.18), radius: 2, y: 1.5)
            Circle().fill(theme.accent).frame(width: 5, height: 5).offset(y: -1.5).opacity(step == 2 ? 1 : 0)
        }
        .rotationEffect(.degrees([-24, 10, -6][step]))
        .scaleEffect(step == 0 ? 0.7 : 1)
        .position([CGPoint(x: 46, y: 46), CGPoint(x: 82, y: 22), CGPoint(x: 112, y: 60)][step])
    }
}

/// Reminders: a box gets ticked and a new reminder slides in.
private struct TickScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            row(done: step >= 1, width: 34)
            row(done: false, width: 26)
            row(done: false, width: 30).opacity(step == 2 ? 1 : 0).offset(x: step == 2 ? 0 : 12)
        }
        .padding(9)
        .frame(width: 72, height: 62, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).strokeBorder(theme.ink.opacity(0.14), lineWidth: 1))
        .position(x: 104, y: 52)
        Actor(emotion: step >= 1 ? .happy : .neutral, gaze: CGVector(dx: 0.6, dy: -0.1), size: 44, at: CGPoint(x: 30, y: 70))
    }

    private func row(done: Bool, width: CGFloat) -> some View {
        HStack(spacing: 5) {
            ZStack {
                Circle().strokeBorder(theme.primary.opacity(0.6), lineWidth: 1.3)
                Circle().fill(theme.primary).scaleEffect(done ? 1 : 0.01)
                CheckBadge.Tick().trim(from: 0, to: done ? 1 : 0)
                    .stroke(theme.onPrimary, style: StrokeStyle(lineWidth: 1.4, lineCap: .round)).padding(2.6)
            }
            .frame(width: 10, height: 10)
            Capsule().fill(theme.ink.opacity(done ? 0.1 : 0.18)).frame(width: width, height: 3.5)
        }
    }
}

/// Mail and Notes: a note fills with lines as Milo writes the draft.
private struct DraftScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Rectangle().fill(theme.glow.opacity(0.7)).frame(height: 9).padding(.horizontal, -8).padding(.top, -8)
            Lines(widths: [44, 50, 34], shown: [0, 2, 3][step])
        }
        .padding(8)
        .frame(width: 66, height: 66, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(theme.card))
        .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(theme.ink.opacity(0.14), lineWidth: 1))
        .position(x: 104, y: 52)
        Actor(state: step == 1 ? .thinking : .idle, emotion: step == 2 ? .happy : .neutral,
              gaze: CGVector(dx: 0.6, dy: 0), size: 44, at: CGPoint(x: 30, y: 70))
        Capsule()
            .fill(theme.accent)
            .frame(width: 4, height: 18)
            .overlay(alignment: .bottom) { Triangle().fill(theme.ink.opacity(0.7)).frame(width: 4, height: 4).offset(y: 3) }
            .rotationEffect(.degrees(35))
            .position([CGPoint(x: 84, y: 40), CGPoint(x: 126, y: 50), CGPoint(x: 112, y: 60)][step])
    }

    struct Triangle: Shape {
        func path(in r: CGRect) -> Path {
            Path { p in
                p.move(to: CGPoint(x: r.minX, y: r.minY))
                p.addLine(to: CGPoint(x: r.maxX, y: r.minY))
                p.addLine(to: CGPoint(x: r.midX, y: r.maxY))
                p.closeSubpath()
            }
        }
    }
}

/// The last step: a key goes down, Milo listens, words appear.
private struct TryScene: View {
    @Environment(\.miloTheme) private var theme
    let step: Int
    let key: String

    var body: some View {
        Actor(state: step >= 1 ? .dictating : .idle, emotion: step == 2 ? .happy : .neutral,
              gaze: CGVector(dx: 0.4, dy: 0.2), at: CGPoint(x: 40, y: 60))
        Text(key)
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(theme.ink)
            .lineLimit(1)
            .frame(minWidth: 34, minHeight: 28)
            .padding(.horizontal, key.count > 2 ? 6 : 0)
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(step >= 1 ? theme.primary.opacity(0.22) : theme.card))
            .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(theme.ink.opacity(0.2), lineWidth: 1))
            .shadow(color: theme.ink.opacity(step >= 1 ? 0.05 : 0.18), radius: 0, y: step >= 1 ? 0.5 : 2.5)
            .offset(y: step >= 1 ? 2 : 0)
            .position(x: 110, y: 72)
        WordChip(text: "Hello!", shown: step == 2, at: CGPoint(x: 104, y: 28))
    }
}
