import AppKit
import SwiftUI

struct BubbleView: View {
    @ObservedObject var model: MiloModel

    var body: some View {
        if let content = content {
            VStack(alignment: .leading, spacing: 6) {
                if let heard = model.heard, model.state == .thinking || model.bubble != nil {
                    Text("“\(heard)”")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                content
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: 270, alignment: .leading)
            .background(BubbleShape().fill(Color(nsColor: .windowBackgroundColor).opacity(0.96)))
            .overlay(BubbleShape().stroke(Color.primary.opacity(0.08), lineWidth: 1))
            .shadow(color: .black.opacity(0.18), radius: 10, y: 4)
            .padding(.trailing, 40)
            .transition(.scale(scale: 0.6, anchor: .bottomTrailing).combined(with: .opacity))
        }
    }

    private var content: AnyView? {
        if let question = model.question, model.state != .listening, model.state != .dictating {
            return AnyView(QuestionView(question: question, answer: model.answer))
        }
        switch model.state {
        case .listening, .dictating:
            let color = model.state == .dictating ? Palette.dictate : Palette.talk
            return AnyView(HStack(spacing: 8) {
                LevelBars(level: model.level, color: color)
                Text(model.state == .dictating ? "Dictating…" : "Listening…")
                    .font(.system(size: 13, weight: .medium))
            })
        case .transcribing where model.bubble == nil:
            return AnyView(ThinkingDots(color: Palette.dictate))
        case .thinking where model.bubble == nil:
            return AnyView(ThinkingDots(color: Palette.think))
        default:
            guard let text = model.bubble else { return nil }
            return AnyView(ScrollView {
                Text(text)
                    .font(.system(size: 13.5))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }
            .scrollIndicators(.never)
            .frame(maxHeight: 170)
            .fixedSize(horizontal: false, vertical: text.count < 260))
        }
    }
}

/// Milo's yes-or-no question with big, plain buttons. A spoken "yes" or "no" on the talk key works too.
struct QuestionView: View {
    let question: PendingQuestion
    let answer: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(question.text)
                .font(.system(size: 13.5, weight: .medium))
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
            AnswerButtons(answer: answer)
        }
    }
}

struct AnswerButtons: View {
    let answer: (Bool) -> Void

    var body: some View {
        HStack(spacing: 8) {
            Button("Yes") { answer(true) }
                .buttonStyle(AnswerButtonStyle(prominent: true))
                .accessibilityHint("Milo goes ahead")
            Button("No") { answer(false) }
                .buttonStyle(AnswerButtonStyle(prominent: false))
                .accessibilityHint("Milo leaves it")
        }
    }
}

/// Drawn by hand: the system's prominent style turns grey in a window without focus, and Milo's
/// floating panel never takes focus.
struct AnswerButtonStyle: ButtonStyle {
    let prominent: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13.5, weight: .semibold, design: .rounded))
            .foregroundStyle(prominent ? Color.white : Color.primary)
            .frame(minWidth: 64)
            .padding(.vertical, 7)
            .padding(.horizontal, 10)
            .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(prominent ? Palette.dictate.blended(dark: 0.25) : Color.primary.opacity(0.08)))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .contentShape(Rectangle())
    }
}

private extension Color {
    /// A shade darker, so white text on Milo's green stays readable.
    func blended(dark fraction: CGFloat) -> Color {
        Color(nsColor: NSColor(self).blended(withFraction: fraction, of: .black) ?? NSColor(self))
    }
}

struct BubbleShape: Shape {
    func path(in rect: CGRect) -> Path {
        let tail: CGFloat = 9
        let body = CGRect(x: rect.minX, y: rect.minY, width: rect.width, height: rect.height - tail)
        var p = Path(roundedRect: body, cornerRadius: 16, style: .continuous)
        let x = body.maxX - 34
        p.move(to: CGPoint(x: x - 10, y: body.maxY))
        p.addQuadCurve(to: CGPoint(x: x + 8, y: rect.maxY), control: CGPoint(x: x + 2, y: body.maxY + 2))
        p.addQuadCurve(to: CGPoint(x: x + 6, y: body.maxY), control: CGPoint(x: x + 6, y: body.maxY + 4))
        p.closeSubpath()
        return p
    }
}

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

struct ThinkingDots: View {
    var color: Color
    @State private var phase = false

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<3) { i in
                Circle()
                    .fill(color)
                    .frame(width: 7, height: 7)
                    .offset(y: phase ? -3 : 3)
                    .animation(.easeInOut(duration: 0.45).repeatForever().delay(Double(i) * 0.15), value: phase)
            }
        }
        .frame(height: 20)
        .onAppear { phase = true }
    }
}
