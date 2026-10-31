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

/// A small Stop button at Milo's side while he talks, thinks or works, or a helper does: one click and he stops
/// everything at once, helpers included. It sits on the left edge of his frame, by his wing; the panel lets a
/// click there through to it instead of starting a drag (`OverlayPanel.stopCenter`).
struct StopByMilo: View {
    /// Plain, simple English; localized where translations exist.
    static let label = String(localized: "Stop Milo", comment: "Button by Milo that stops what he is doing")
    static let tip = String(localized: "Stop Milo and his helpers", comment: "Tooltip of the Stop button by Milo")
    static let size: CGFloat = 28
    /// From the middle of the left edge of his 132 pt frame.
    static let offset = CGSize(width: -8, height: 4)

    @Environment(\.miloTheme) private var theme
    @ObservedObject var model: MiloModel

    var body: some View {
        if model.canStop {
            Button(action: model.stopAll) {
                Image(systemName: "stop.fill")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(theme.primary)
                    .frame(width: Self.size, height: Self.size)
                    .floatingSurface(Circle())
                    .contentShape(Circle())
            }
            .buttonStyle(.plain)
            .help(Self.tip)
            .accessibilityLabel(Self.label)
            .transition(.scale(scale: 0.4).combined(with: .opacity))
        }
    }
}
