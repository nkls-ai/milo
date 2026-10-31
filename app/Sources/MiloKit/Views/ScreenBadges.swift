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

/// A small Stop button by Milo while he talks, thinks or works: one click and he stops everything at once.
struct StopByMilo: View {
    /// Plain, simple English; localized where translations exist.
    static let label = String(localized: "Stop Milo", comment: "Button by Milo that stops what he is doing")

    @Environment(\.miloTheme) private var theme
    @ObservedObject var model: MiloModel

    var body: some View {
        if model.canStop {
            Button(action: model.stopAll) {
                Image(systemName: "stop.fill")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(theme.primary)
                    .frame(width: 30, height: 30)
                    .floatingSurface(Circle())
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .help(Self.label)
            .accessibilityLabel(Self.label)
            .transition(.scale(scale: 0.4).combined(with: .opacity))
        }
    }
}
