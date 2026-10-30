import SwiftUI

/// The words heard so far, in a small pill next to Milo while recording. A lock marks hands-free mode.
struct LiveTranscriptView: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var model: MiloModel

    var body: some View {
        if let line {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if model.handsFree != nil {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(color)
                }
                Text(line)
                    .font(.system(size: 12))
                    .foregroundStyle(model.partial == nil ? theme.ink.opacity(0.6) : theme.ink)
                    .lineLimit(3)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .frame(maxWidth: 250, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 13, style: .continuous)
                .fill(theme.tint.opacity(0.96)))
            .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(color.opacity(0.55), lineWidth: 1))
            .shadow(color: theme.primary.opacity(0.18), radius: 7, y: 3)
            .padding(.trailing, 40)
            .transition(.opacity.combined(with: .scale(scale: 0.9, anchor: .bottomTrailing)))
            .animation(theme.motion.spring, value: line)
        }
    }

    private var line: String? {
        let recording = model.state == .listening || model.state == .dictating || model.state == .transcribing
        guard recording || model.handsFree != nil else { return nil }
        if let partial = model.partial { return Self.tail(partial) }
        return model.handsFree != nil ? "Hands-free. Tap the key again to finish, esc to cancel." : nil
    }

    private var color: Color {
        (model.handsFree ?? (model.state == .listening ? .talk : .dictate)) == .talk ? theme.primary : theme.accent
    }

    /// The last `limit` characters, cut at a word, so the newest words stay visible.
    static func tail(_ text: String, limit: Int = 140) -> String {
        guard text.count > limit else { return text }
        let end = text.suffix(limit + 1)
        let start = end.firstIndex(of: " ").map { end.index(after: $0) } ?? end.startIndex
        return "…" + end[start...]
    }
}
