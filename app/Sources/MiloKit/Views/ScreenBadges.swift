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

/// A red dot on Milo while he records a meeting.
struct RecordingBadge: View {
    @ObservedObject var model: MiloModel
    @State private var pulse = false

    var body: some View {
        if model.recording {
            Circle()
                .fill(Color.red)
                .frame(width: 12, height: 12)
                .overlay(Circle().stroke(Color.white, lineWidth: 2))
                .opacity(pulse ? 0.55 : 1)
                .shadow(color: .black.opacity(0.2), radius: 3, y: 1)
                .padding(4)
                .onAppear {
                    withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true)) { pulse = true }
                }
                .onDisappear { pulse = false }
                .transition(.scale.combined(with: .opacity))
                .accessibilityLabel("Milo is taking meeting notes")
        }
    }
}
