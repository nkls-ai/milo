import SwiftUI

/// A soft border in Milo's colours around the window Milo is working in, with a small "Milo is working here" tag.
/// Fills its panel; the panel is placed over the window and follows it. Clicks go through it to the window: the
/// Stop button is by Milo (`StopByMilo`).
struct WorkingOutlineView: View {
    /// Plain, simple English; localized where translations exist.
    static let label = String(localized: "Milo is working here",
                              comment: "Tag on the outline of the window Milo is using")

    /// His theme; the outline passes a new one when `[ui] character` changes.
    var theme = Theme.for(.milo)

    var body: some View {
        WorkingEdge(theme: theme, radius: 12, width: 3)
            .overlay(alignment: .topLeading) {
                WorkingTag(text: Self.label, theme: theme).padding(10)
            }
            .padding(2)
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
