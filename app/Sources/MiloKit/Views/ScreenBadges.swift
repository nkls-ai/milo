import SwiftUI

/// The small eye on Milo while he looks at the screen. Drawn over the character, so it needs no change to
/// the character itself.
struct LookingBadge: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var model: MiloModel

    var body: some View {
        if model.looking {
            Image(systemName: "eye.fill")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(theme.primary)
                .frame(width: Surface.badgeSize, height: Surface.badgeSize)
                .floatingSurface(Circle())
                .transition(.scale(scale: 0.4).combined(with: .opacity))
                .accessibilityLabel("Milo is looking at the screen")
        }
    }
}
