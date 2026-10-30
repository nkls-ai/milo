import SwiftUI

// Small pieces the Settings and setup windows share, all in the active skin's theme.

/// A soft card on the window's tinted paper.
struct ThemedCard<Content: View>: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    var padding: CGFloat = 16
    @ViewBuilder var content: Content

    var body: some View {
        let (line, width) = Surface.edge(theme, contrast)
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(theme.card))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(line, lineWidth: width))
            .shadow(color: theme.primary.opacity(0.07), radius: 12, y: 4)
    }
}

/// A heading over a card: a small icon in the skin's colour, a title, and a line in plain words.
struct CardHeading: View {
    @Environment(\.miloTheme) private var theme
    let icon: String
    let title: String
    var detail: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(theme.primary)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink)
                if let detail {
                    Text(detail)
                        .font(.system(size: 12))
                        .foregroundStyle(theme.ink.opacity(0.6))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

/// A rounded button in the skin's colour, or a quiet one on a light wash. Presses with a little squash.
struct PillButtonStyle: ButtonStyle {
    @Environment(\.miloTheme) private var theme
    @Environment(\.isEnabled) private var enabled
    var prominent = true

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .foregroundStyle(prominent ? theme.onPrimary : theme.primary)
            .padding(.horizontal, 14)
            .padding(.vertical, 7)
            .background(Capsule().fill(prominent ? theme.primary : theme.primary.opacity(0.12)))
            .opacity(enabled ? 1 : 0.5)
            .scaleEffect(configuration.isPressed ? 0.94 : 1)
            .animation(theme.motion.spring, value: configuration.isPressed)
            .contentShape(Capsule())
    }
}

/// An empty ring until something is done, then a filled circle whose tick draws itself, with a soft burst.
struct CheckBadge: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let done: Bool
    var size: CGFloat = 24

    var body: some View {
        ZStack {
            Circle()
                .stroke(theme.primary.opacity(done ? 0 : 0.28), style: StrokeStyle(lineWidth: 1.6, dash: [3, 3]))
            Circle()
                .stroke(theme.glow, lineWidth: 2)
                .scaleEffect(done ? 1.9 : 1)
                .opacity(done ? 0 : 0.0001)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.6), value: done)
            Circle()
                .fill(theme.primary)
                .scaleEffect(done ? 1 : 0.2)
                .opacity(done ? 1 : 0)
            Tick()
                .trim(from: 0, to: done ? 1 : 0)
                .stroke(theme.onPrimary, style: StrokeStyle(lineWidth: size * 0.11, lineCap: .round, lineJoin: .round))
                .padding(size * 0.27)
                .animation(reduceMotion ? nil : theme.motion.spring.delay(0.12), value: done)
        }
        .frame(width: size, height: size)
        .animation(theme.motion.animation(reduced: reduceMotion), value: done)
        .accessibilityHidden(true)
    }

    struct Tick: Shape {
        func path(in rect: CGRect) -> Path {
            var p = Path()
            p.move(to: CGPoint(x: rect.minX, y: rect.midY + rect.height * 0.05))
            p.addLine(to: CGPoint(x: rect.minX + rect.width * 0.36, y: rect.maxY - rect.height * 0.08))
            p.addLine(to: CGPoint(x: rect.maxX, y: rect.minY + rect.height * 0.1))
            return p
        }
    }
}

/// A few choices as rows, all visible. The chosen one gets a wash and a filled dot that springs in.
struct ChoiceList: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let choices: [(value: JSONValue, label: String)]
    let selected: JSONValue
    let choose: (JSONValue) -> Void
    @State private var hovered: String?

    var body: some View {
        VStack(spacing: 4) {
            ForEach(choices, id: \.label) { choice in
                let on = choice.value == selected
                Button {
                    choose(choice.value)
                } label: {
                    HStack(spacing: 10) {
                        ZStack {
                            Circle().strokeBorder(on ? theme.primary : theme.ink.opacity(0.25), lineWidth: 1.5)
                            Circle().fill(theme.primary).padding(4).scaleEffect(on ? 1 : 0.01)
                        }
                        .frame(width: 16, height: 16)
                        Text(choice.label)
                            .font(.system(size: 13, weight: on ? .semibold : .regular))
                            .foregroundStyle(theme.ink.opacity(on ? 1 : 0.8))
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(on ? theme.primary.opacity(0.12)
                                 : hovered == choice.label ? theme.ink.opacity(0.04) : .clear))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .onHover { hovered = $0 ? choice.label : (hovered == choice.label ? nil : hovered) }
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .animation(theme.motion.animation(reduced: reduceMotion), value: selected)
    }
}

/// A note under a card in plain words, with an optional button: "Fix it", "Restart Milo".
struct Callout: View {
    @Environment(\.miloTheme) private var theme
    let icon: String
    let text: String
    var button: String?
    var action: () -> Void = {}

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(theme.accent)
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(theme.ink.opacity(0.8))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            if let button {
                Button(button, action: action).buttonStyle(PillButtonStyle(prominent: false))
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(theme.accent.opacity(0.09)))
        .transition(.opacity.combined(with: .move(edge: .top)))
    }
}
