import SwiftUI

/// A soft lavender border around the window Milo is working in, with a small "Milo is working here" tag and
/// a Stop button. Fills its panel; the panel is placed over the window and follows it.
struct WorkingOutlineView: View {
    /// Plain, simple English; localized where translations exist.
    static let label = String(localized: "Milo is working here",
                              comment: "Tag on the outline of the window Milo is using")
    static let stop = String(localized: "Stop", comment: "Button to stop Milo working")

    var onStop: () -> Void
    @State private var glow = false

    var body: some View {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
            .strokeBorder(LinearGradient(colors: [Palette.bodyTop, Palette.speak, Palette.bodyBottom],
                                         startPoint: .topLeading, endPoint: .bottomTrailing),
                          lineWidth: 3)
            .opacity(glow ? 0.9 : 0.55)
            .overlay(alignment: .topLeading) { tag.padding(10) }
            .padding(2)
            .onAppear { withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) { glow = true } }
    }

    private var tag: some View {
        HStack(spacing: 8) {
            Text(Self.label)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.white)
            Button(action: onStop) {
                Text(Self.stop).font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(Capsule().fill(.white.opacity(0.22)))
            .foregroundStyle(.white)
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background(Capsule().fill(Palette.bodyBottom.opacity(0.92)))
        .shadow(color: .black.opacity(0.25), radius: 5, y: 1)
    }
}
