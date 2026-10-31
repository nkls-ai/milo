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
            return AnyView(QuestionView(question: question, answer: { model.answer($0) }, choose: { model.answer($0) }))
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
                Button(action: act) {
                    if let icon = action.icon {
                        Label(action.title, systemImage: icon).labelStyle(TightLabel())
                    } else {
                        Text(action.title)
                    }
                }
                // Undo sits under what Milo says about the task, quieter than a button that fixes something.
                .buttonStyle(AnswerButtonStyle(prominent: action.icon == nil))
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

/// Milo's yes-or-no question with big, plain buttons. A spoken "yes" or "no" on the talk key works too, except for a
/// question about money: it says so at the top, and only a click on Yes answers it (ADR 23).
struct QuestionView: View {
    @Environment(\.miloTheme) private var theme
    let question: PendingQuestion
    let answer: (Answer) -> Void
    var choose: (ConfirmChoice) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(heading, systemImage: icon)
                .font(.system(size: 10.5, weight: .semibold, design: .rounded))
                .foregroundStyle(theme.accent)
                .labelStyle(TightLabel())
            Text(question.text)
                .font(.system(size: 13.5, weight: .medium))
                // The brain sends at most 240 characters (approvals.fit_bubble), which fit in 8 lines: a question
                // is never cut here, so Yes never sits under a hidden end. The limit only keeps Milo on screen.
                .lineLimit(8)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
                .help(question.text)
            if question.money {
                Text(QuestionView.moneyNote)
                    .font(.system(size: 11))
                    .foregroundStyle(theme.ink.opacity(0.65))
                    .fixedSize(horizontal: false, vertical: true)
            }
            AnswerButtons(always: question.always, choices: question.choices, answer: answer, choose: choose)
                .padding(.top, 2)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(question.money ? "Milo asks about money: \(question.text)" : "Milo asks: \(question.text)")
    }
}

extension QuestionView {
    /// Under a money question, in the bubble, the window and Today.
    static let moneyNote = "Only a click on Yes counts for this, not a spoken yes."

    /// Money first, then a question with its own buttons ("Up to you"), else the plain heading.
    var heading: String {
        question.money ? "This involves money" : question.choices.isEmpty ? "Okay to go ahead?" : "Up to you"
    }

    var icon: String {
        question.money ? "creditcard.fill" : question.choices.isEmpty ? "hand.raised.fill" : "questionmark.bubble.fill"
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

/// Yes and No, or for a question about working in an app, Allow, Allow always and No (ADR 22). The three are a
/// little narrower, so they fit in one row even in the bubble: a second row would push an eight-line question's
/// top out of Milo's panel. Should they not fit, Allow always goes on a line of its own.
///
/// A question with choices of its own shows only those: its yes and no first, the rest, like "Always for Zoom",
/// smaller under them. Its "always" is the asker's own (the meeting question's), never Allow always.
struct AnswerButtons: View {
    var always = false
    var choices: [ConfirmChoice] = []
    let answer: (Answer) -> Void
    var choose: (ConfirmChoice) -> Void = { _ in }

    var body: some View {
        if !choices.isEmpty {
            let main = choices.filter { $0.id == "yes" || $0.id == "no" }
            let more = choices.filter { $0.id != "yes" && $0.id != "no" }
            VStack(alignment: .leading, spacing: 7) {
                HStack(spacing: 8) {
                    ForEach(main, id: \.id) { choice in
                        Button(choice.label) { choose(choice) }
                            .buttonStyle(AnswerButtonStyle(prominent: choice.id == "yes"))
                    }
                }
                if !more.isEmpty {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 6) { quiet(more) }
                        VStack(alignment: .leading, spacing: 6) { quiet(more) }
                    }
                }
            }
        } else if always {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) { allow; allowAlways; no }
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 8) { allow; no }
                    allowAlways
                }
            }
        } else {
            HStack(spacing: 8) {
                Button("Yes") { answer(.yes) }
                    .buttonStyle(AnswerButtonStyle(prominent: true))
                    .accessibilityHint("Milo goes ahead")
                no
            }
        }
    }

    private var allow: some View {
        Button("Allow") { answer(.yes) }
            .buttonStyle(AnswerButtonStyle(prominent: true, compact: always))
            .accessibilityHint("Milo goes ahead, and doesn't ask again about this work in this app until the task is done")
    }

    private var allowAlways: some View {
        Button("Allow always") { answer(.always) }
            .buttonStyle(AnswerButtonStyle(prominent: false, compact: true))
            .accessibilityHint("Milo won't ask about work in this app again. Take it back in Settings.")
            .help("Milo won't ask about work in this app again. Things that can't be undone, sending, buying and "
                  + "money still ask. Take it back in Settings.")
    }

    private var no: some View {
        Button("No") { answer(.no) }
            .buttonStyle(AnswerButtonStyle(prominent: false, compact: always))
            .accessibilityHint("Milo leaves it")
    }

    private func quiet(_ list: [ConfirmChoice]) -> some View {
        ForEach(list, id: \.id) { choice in
            Button(choice.label) { choose(choice) }
                .buttonStyle(QuietChoiceStyle())
                .accessibilityHint(choice.id == "always" ? "Milo won't ask again and takes notes every time"
                                   : choice.id == "never" ? "Milo won't ask again for this app" : "")
        }
    }
}

/// A small, quiet button for a choice past Yes and No: "Always for Zoom".
struct QuietChoiceStyle: ButtonStyle {
    @Environment(\.miloTheme) private var theme
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .medium, design: .rounded))
            .foregroundStyle(theme.ink.opacity(0.8))
            .lineLimit(1)
            .fixedSize()
            .padding(.vertical, 5)
            .padding(.horizontal, 9)
            .background(Capsule(style: .continuous).fill(theme.ink.opacity(hovered ? 0.1 : 0.055)))
            .scaleEffect(configuration.isPressed ? 0.95 : 1)
            .animation(theme.motion.spring, value: configuration.isPressed)
            .contentShape(Capsule())
            .onHover { hovered = $0 }
    }
}

/// Drawn by hand: the system's prominent style turns grey in a window without focus, and Milo's
/// floating panel never takes focus.
struct AnswerButtonStyle: ButtonStyle {
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    let prominent: Bool
    /// Narrower, for three buttons in a row.
    var compact = false
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: Surface.controlRadius, style: .continuous)
        return configuration.label
            .font(.system(size: 13.5, weight: .semibold, design: .rounded))
            .foregroundStyle(prominent ? theme.onPrimary : theme.ink)
            .frame(minWidth: compact ? 34 : 64)
            .padding(.vertical, 7)
            .padding(.horizontal, compact ? 9 : 10)
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
