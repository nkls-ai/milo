import SwiftUI

/// A soft border in Milo's colours around the window Milo is working in, with a small "Milo is working here" tag and
/// a Stop button. Fills its panel; the panel is placed over the window and follows it.
struct WorkingOutlineView: View {
    /// Plain, simple English; localized where translations exist.
    static let label = String(localized: "Milo is working here",
                              comment: "Tag on the outline of the window Milo is using")
    static let stop = String(localized: "Stop", comment: "Button to stop Milo working")

    var onStop: () -> Void
    /// His theme; the outline passes a new one when `[ui] character` changes.
    var theme = Theme.for(.milo)

    var body: some View {
        WorkingEdge(theme: theme, radius: 12, width: 3)
            .overlay(alignment: .topLeading) {
                WorkingTag(text: Self.label, theme: theme, stop: (Self.stop, onStop)).padding(10)
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

/// The tag that says what Milo is doing with your screen, with a Stop button when there is one.
struct WorkingTag: View {
    let text: String
    let theme: Theme
    var stop: (title: String, action: () -> Void)?

    var body: some View {
        HStack(spacing: 10) {
            Text(text)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
            if let stop {
                Button(action: stop.action) {
                    Label(stop.title, systemImage: "stop.fill")
                        .labelStyle(TightLabel())
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 3)
                        .background(Capsule().fill(theme.onPrimary.opacity(0.24)))
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .help("Stop Milo. Esc works too.")
            }
        }
        .foregroundStyle(theme.onPrimary)
        .padding(.leading, 12)
        .padding(.trailing, stop == nil ? 12 : 5)
        .padding(.vertical, 5)
        .background(Capsule().fill(theme.primary.opacity(0.94)).shadow(color: .black.opacity(0.22), radius: 5, y: 1))
        .accessibilityElement(children: .contain)
    }
}
