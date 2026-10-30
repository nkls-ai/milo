import SwiftUI

/// The small eye on Milo while he looks at the screen. Drawn over the character, so it needs no change to
/// the character itself.
struct LookingBadge: View {
    @ObservedObject var model: MiloModel

    var body: some View {
        if model.looking {
            Image(systemName: "eye.fill")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Palette.face)
                .padding(6)
                .background(Circle().fill(Palette.speak))
                .shadow(color: .black.opacity(0.2), radius: 3, y: 1)
                .transition(.scale.combined(with: .opacity))
                .accessibilityLabel("Milo is looking at the screen")
        }
    }
}
