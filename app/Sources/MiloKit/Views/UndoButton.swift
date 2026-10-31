import SwiftUI

/// Undo on a finished task (ADR 0024): a small button while it can be undone, then "Undoing…" and "Undone".
struct UndoButton: View {
    @Environment(\.miloTheme) private var theme
    let point: UndoPoint
    let undo: (String) -> Void

    var body: some View {
        switch point.state {
        case .ready:
            Button { undo(point.id) } label: {
                Label("Undo", systemImage: "arrow.uturn.backward").labelStyle(TightLabel())
            }
            .buttonStyle(UndoButtonStyle())
            .help("Put back what Milo changed in “\(point.title)”")
            .accessibilityHint("Puts back what Milo changed in this task")
        case .undoing:
            Label("Undoing…", systemImage: "arrow.uturn.backward")
                .labelStyle(TightLabel())
                .font(.system(size: 11.5, weight: .medium, design: .rounded))
                .foregroundStyle(theme.ink.opacity(0.55))
        case .undone:
            Label("Undone", systemImage: "arrow.uturn.backward.circle")
                .labelStyle(TightLabel())
                .font(.system(size: 11.5, weight: .medium, design: .rounded))
                .foregroundStyle(theme.ink.opacity(0.5))
                .accessibilityLabel("Undone: Milo put back what this task changed")
        }
    }
}

struct UndoButtonStyle: ButtonStyle {
    @Environment(\.miloTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        let shape = RoundedRectangle(cornerRadius: 8, style: .continuous)
        return configuration.label
            .font(.system(size: 11.5, weight: .semibold, design: .rounded))
            .foregroundStyle(theme.primary)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(shape.fill(theme.primary.opacity(hovered ? 0.16 : 0.09)))
            .overlay(shape.strokeBorder(theme.primary.opacity(contrast == .increased ? 0.8 : 0.3), lineWidth: 1))
            .scaleEffect(configuration.isPressed ? 0.95 : 1)
            .animation(theme.motion.spring, value: configuration.isPressed)
            .contentShape(shape)
            .onHover { hovered = $0 }
    }
}
