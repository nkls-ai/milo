import SwiftUI

/// A soft border in Milo's colours around the window Milo is working in, with a small "Milo is working here" tag.
/// Fills its panel; the panel is placed over the window and follows it. Clicks go through it to the window: the
/// Stop button is by Milo (`StopByMilo`).
struct WorkingOutlineView: View {
    /// Plain, simple English; localized where translations exist.
    static let label = String(localized: "Milo is working here",
                              comment: "Tag on the outline of the window Milo is using")

    /// His colours.
    var theme = Theme.milo
    /// What he does right now, in plain words (`MiloModel.workingStep`); nil shows no caption.
    var caption: String?
    /// The panel has `captionRoom` points below the window: the caption sits on the bottom edge, half outside.
    /// Without it (a window down to the screen's edge) the caption sits just inside.
    var below = true

    /// Points the panel reaches below the window's outline for the caption.
    static let captionRoom: CGFloat = 14

    var body: some View {
        WorkingEdge(theme: theme, radius: 12, width: 3)
            .overlay(alignment: .topLeading) {
                WorkingTag(text: Self.label, theme: theme).padding(10)
            }
            .padding(2)
            .padding(.bottom, below ? Self.captionRoom : 0)
            .overlay(alignment: .bottom) {
                ZStack {
                    if let caption {
                        WorkingCaption(text: caption, theme: theme)
                            .id(caption)
                            .transition(.opacity)
                    }
                }
                .padding(.bottom, below ? 0 : 10)
                .padding(.horizontal, 24)
                .animation(.easeInOut(duration: 0.18), value: caption)
            }
    }
}

/// The current step under the outline: "Typing “youtube.com” in Safari". A small paper pill on the window's bottom
/// edge, with a lavender dot that means Milo's hands are at it.
struct WorkingCaption: View {
    let text: String
    let theme: Theme
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(theme.primary).frame(width: 6, height: 6)
            Text(text)
                .font(.system(size: 11.5, weight: .semibold, design: .rounded))
                .foregroundStyle(theme.ink)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.horizontal, 11)
        .frame(height: 24)
        .background(Capsule().fill(theme.tint.opacity(contrast == .increased ? 1 : 0.97))
            .shadow(color: theme.primary.opacity(0.25), radius: 6, y: 2))
        .overlay(Capsule().strokeBorder(contrast == .increased ? theme.ink.opacity(0.6) : theme.primary.opacity(0.35),
                                        lineWidth: contrast == .increased ? 1.5 : 1))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Milo: \(text)")
    }
}

/// The glowing edge around where Milo works, in Milo's colours. It breathes slowly, or holds still with
/// Reduce Motion; with Increase Contrast it is thicker and steady.
struct WorkingEdge: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorSchemeContrast) private var contrast
    let theme: Theme
    let radius: CGFloat
    let width: CGFloat
    var blur: CGFloat = 0
    @State private var glow = false

    var body: some View {
        let strong = contrast == .increased
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .strokeBorder(LinearGradient(colors: [theme.glow, theme.accent, theme.primary],
                                         startPoint: .topLeading, endPoint: .bottomTrailing),
                          lineWidth: strong ? width + 2 : width)
            .opacity(strong ? 1 : glow ? 0.9 : 0.55)
            .blur(radius: strong ? 0 : blur)
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) { glow = true }
            }
    }
}

/// The tag that says what Milo is doing with your screen.
struct WorkingTag: View {
    let text: String
    let theme: Theme

    var body: some View {
        Text(text)
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(theme.onPrimary)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(Capsule().fill(theme.primary.opacity(0.94)).shadow(color: .black.opacity(0.22), radius: 5, y: 1))
            .accessibilityElement(children: .combine)
    }
}
