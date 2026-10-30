import SwiftUI

/// Sizes every floating surface next to Milo shares, so the bubble, the voice capsule and the badges read as
/// one family: one corner radius per kind of thing, one width for text, one shadow.
enum Surface {
    /// The answer bubble.
    static let bubbleRadius: CGFloat = 16
    /// The voice capsule: nearly a pill on one line, a soft card when the words wrap. Under half its 30 pt height:
    /// a border at exactly half draws a short bar at each end.
    static let capsuleRadius: CGFloat = 13
    /// Buttons inside a bubble.
    static let controlRadius: CGFloat = 9
    /// The widest a line of text runs next to Milo.
    static let textWidth: CGFloat = 246
    /// The bubble and the capsule end this far left of the panel's right edge, so the tail points at Milo's head.
    static let trailingInset: CGFloat = 40
    /// Small round marks on Milo: looking, recording.
    static let badgeSize: CGFloat = 24

    /// The edge of a card or a floating surface: a hairline, or a real line with Increase Contrast.
    static func edge(_ theme: Theme, _ contrast: ColorSchemeContrast, tint: Color? = nil) -> (Color, CGFloat) {
        contrast == .increased ? (theme.ink.opacity(0.6), 1.5) : (tint ?? theme.rule, 1)
    }

    /// The colour a recording mode wears: lavender to talk to Milo, marigold to dictate.
    static func color(for mode: ListenMode?, _ theme: Theme) -> Color {
        mode == .dictate ? theme.accent : theme.primary
    }
}

extension View {
    /// The paper, hairline and soft lift of a surface floating next to Milo, in the active theme. With Increase
    /// Contrast the paper is opaque and the edge is a real line.
    func floatingSurface<S: InsettableShape>(_ shape: S, edge: Color? = nil) -> some View {
        modifier(FloatingSurface(shape: shape, edge: edge))
    }
}

private struct FloatingSurface<S: InsettableShape>: ViewModifier {
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    let shape: S
    /// A coloured edge instead of the hairline, for a surface that belongs to a mode.
    let edge: Color?

    func body(content: Content) -> some View {
        let strong = contrast == .increased
        let (line, width) = Surface.edge(theme, contrast, tint: edge)
        // The shadow falls from the paper alone: a shadow on the whole surface would blur its text too, several
        // times the work for every frame of every change.
        content
            .background(shape.fill(theme.tint.opacity(strong ? 1 : 0.97))
                .shadow(color: theme.primary.opacity(0.2), radius: 12, y: 5))
            .overlay(shape.strokeBorder(line, lineWidth: width))
    }
}

/// Lets its content be at most `width` by `height` and no bigger than it wants to be. A `.frame(maxWidth:)`
/// would stretch a short bubble to the full width instead of letting it hug its words.
struct Capped: SwiftUI.Layout {
    var width: CGFloat?
    var height: CGFloat?

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        subviews.first?.sizeThatFits(capped(proposal)) ?? .zero
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        subviews.first?.place(at: bounds.origin, proposal: ProposedViewSize(bounds.size))
    }

    private func capped(_ proposal: ProposedViewSize) -> ProposedViewSize {
        func cap(_ value: CGFloat?, _ limit: CGFloat?) -> CGFloat? {
            guard let limit else { return value }
            return min(value ?? limit, limit)
        }
        return ProposedViewSize(width: cap(proposal.width, width), height: cap(proposal.height, height))
    }
}
