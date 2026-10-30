import SwiftUI

/// Milo's speech bubble: his answer with the words in step with his voice, a question waiting for Yes or No,
/// or a note with a button that fixes what it is about. It steps aside while the user records.
struct BubbleView: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var model: MiloModel

    var body: some View {
        if let content {
            Capped(width: Surface.textWidth) { content }
                .foregroundStyle(theme.ink)
                .padding(.horizontal, 14)
                .padding(.top, 10)
                .padding(.bottom, 10 + BubbleShape.tail)
                .floatingSurface(BubbleShape())
                .padding(.trailing, Surface.trailingInset)
                .transition(reduceMotion ? .opacity
                                         : .scale(scale: 0.6, anchor: .bottomTrailing).combined(with: .opacity))
        }
    }

    private var content: AnyView? {
        let phase = model.voicePhase
        if phase?.recording == true { return nil }
        if let question = model.question {
            return AnyView(QuestionView(question: question, answer: model.answer))
        }
        if case .transcribing = phase { return nil }
        guard let text = model.bubble else { return nil }
        return AnyView(MessageView(text: text, heard: model.heard, reveal: model.reveal, now: model.now,
                                   action: model.bubbleAction, act: model.performBubbleAction))
    }
}

/// An answer or a note: what the user asked, small, then Milo's words, then the button if there is one.
struct MessageView: View {
    @Environment(\.miloTheme) private var theme
    let text: String
    let heard: String?
    let reveal: SpeechReveal
    let now: () -> TimeInterval
    let action: BubbleAction?
    let act: () -> Void
    /// Longer answers scroll, kept at their newest words.
    static let tallest: CGFloat = 200

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let heard {
                Text("“\(heard)”")
                    .font(.system(size: 11))
                    .foregroundStyle(theme.ink.opacity(0.55))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Capped(height: Self.tallest) {
                ViewThatFits(in: .vertical) {
                    words
                    ScrollView { words }
                        .scrollIndicators(.never)
                        .defaultScrollAnchor(.bottom)
                }
            }
            if let action {
                Button(action.title, action: act)
                    .buttonStyle(AnswerButtonStyle(prominent: true))
                    .accessibilityHint(action.hint)
                    .padding(.top, 4)
            }
        }
    }

    private var words: some View {
        RevealingText(text: text, reveal: reveal, now: now)
            .font(.system(size: 13.5))
            .lineSpacing(1.5)
            .fixedSize(horizontal: false, vertical: true)
            .textSelection(.enabled)
    }
}

/// Text whose words show in step with Milo's voice. The whole piece is laid out from the start, the words not
/// said yet are only transparent, so lines never reflow while it fills in.
struct RevealingText: View {
    @Environment(\.miloTheme) private var theme
    let text: String
    let reveal: SpeechReveal
    let now: () -> TimeInterval

    var body: some View {
        Group {
            if reveal.paced && reveal.text == text {
                TimelineView(.animation(minimumInterval: 1 / 30)) { _ in
                    draw(reveal.cut(at: now()))
                }
            } else {
                Text(text)
            }
        }
        .accessibilityLabel(text)
    }

    private func draw(_ cut: (shown: Int, fresh: Int, alpha: Double)) -> Text {
        let chars = Array(text)
        let fresh = cut.shown + cut.fresh
        return Text(String(chars[..<cut.shown]))
            + Text(String(chars[cut.shown..<fresh])).foregroundStyle(theme.ink.opacity(cut.alpha))
            + Text(String(chars[fresh...])).foregroundStyle(.clear)
    }
}

/// Milo's yes-or-no question with big, plain buttons. A spoken "yes" or "no" on the talk key works too.
struct QuestionView: View {
    @Environment(\.miloTheme) private var theme
    let question: PendingQuestion
    let answer: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("Okay to go ahead?", systemImage: "hand.raised.fill")
                .font(.system(size: 10.5, weight: .semibold, design: .rounded))
                .foregroundStyle(theme.accent)
                .labelStyle(TightLabel())
            Text(question.text)
                .font(.system(size: 13.5, weight: .medium))
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
            AnswerButtons(answer: answer)
                .padding(.top, 2)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Milo asks: \(question.text)")
    }
}

/// An icon and a title, closer together than the system's label.
struct TightLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 5) {
            configuration.icon
            configuration.title
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
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    let prominent: Bool
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: Surface.controlRadius, style: .continuous)
        return configuration.label
            .font(.system(size: 13.5, weight: .semibold, design: .rounded))
            .foregroundStyle(prominent ? theme.onPrimary : theme.ink)
            .frame(minWidth: 64)
            .padding(.vertical, 7)
            .padding(.horizontal, 10)
            .background(shape.fill(prominent ? theme.primary : theme.ink.opacity(hovered ? 0.12 : 0.08)))
            .overlay(shape.strokeBorder(theme.ink.opacity(contrast == .increased && !prominent ? 0.5 : 0)))
            .brightness(prominent && hovered ? 0.04 : 0)
            .scaleEffect(configuration.isPressed ? 0.95 : 1)
            .animation(theme.motion.spring, value: configuration.isPressed)
            .contentShape(shape)
            .onHover { hovered = $0 }
    }
}

/// A rounded bubble with a small tail at the bottom right, pointing down at Milo.
struct BubbleShape: InsettableShape {
    static let tail: CGFloat = 8
    var inset: CGFloat = 0

    /// One outline around the body and the tail, so the edge runs into the tail without a seam.
    func path(in rect: CGRect) -> Path {
        let rect = rect.insetBy(dx: inset, dy: inset)
        let r = max(0, Surface.bubbleRadius - inset)
        let bottom = rect.maxY - Self.tail + inset
        let x = rect.maxX - 34 + inset
        var p = Path()
        p.move(to: CGPoint(x: rect.minX + r, y: rect.minY))
        p.addArc(tangent1End: CGPoint(x: rect.maxX, y: rect.minY), tangent2End: CGPoint(x: rect.maxX, y: bottom), radius: r)
        p.addArc(tangent1End: CGPoint(x: rect.maxX, y: bottom), tangent2End: CGPoint(x: rect.minX, y: bottom), radius: r)
        p.addLine(to: CGPoint(x: x + 6, y: bottom))
        p.addQuadCurve(to: CGPoint(x: x + 8, y: rect.maxY), control: CGPoint(x: x + 6, y: bottom + 4))
        p.addQuadCurve(to: CGPoint(x: x - 10, y: bottom), control: CGPoint(x: x + 2, y: bottom + 2))
        p.addArc(tangent1End: CGPoint(x: rect.minX, y: bottom), tangent2End: CGPoint(x: rect.minX, y: rect.minY), radius: r)
        p.addArc(tangent1End: CGPoint(x: rect.minX, y: rect.minY), tangent2End: CGPoint(x: rect.maxX, y: rect.minY), radius: r)
        p.closeSubpath()
        return p
    }

    func inset(by amount: CGFloat) -> BubbleShape {
        var shape = self
        shape.inset += amount
        return shape
    }
}
