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

/// A yes-or-no question before something that can't be undone. No answer counts as no.
struct QuestionView: View {
    let question: MiloModel.Question
    let answer: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(question.text)
                .font(.system(size: 13.5, weight: .medium))
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Spacer(minLength: 0)
                Button("No") { answer(false) }
                    .keyboardShortcut(.cancelAction)
                Button("Yes") { answer(true) }
                    .buttonStyle(.borderedProminent)
            }
            .controlSize(.regular)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: 270, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(Color(nsColor: .windowBackgroundColor).opacity(0.97)))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Palette.think.opacity(0.8), lineWidth: 1.5))
        .shadow(color: .black.opacity(0.18), radius: 10, y: 4)
        .padding(.trailing, 40)
        .transition(.scale(scale: 0.6, anchor: .bottomTrailing).combined(with: .opacity))
    }
}
