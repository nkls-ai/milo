import SwiftUI

/// The capsule over Milo while he takes meeting notes: a red light, "Taking notes", the time so far, Pause and a
/// clear Stop. Paused, the light goes grey and Pause turns into Go on. After Stop it says what he writes until the
/// notes are ready. A click anywhere else on it opens the meeting's page. See docs/design/meetings.md.
struct MeetingCapsule: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var meeting: MeetingModel

    var body: some View {
        ZStack(alignment: .trailing) { content }
            .animation(theme.motion.animation(reduced: reduceMotion), value: meeting.status.phase)
            .animation(theme.motion.animation(reduced: reduceMotion), value: meeting.status.step)
    }

    @ViewBuilder private var content: some View {
        let status = meeting.status
        if status.live || status.phase == .writing {
            HStack(spacing: 8) {
                Button { meeting.open(status.id) } label: { label(status) }
                    .buttonStyle(.plain)
                    .help("Open the meeting's page")
                    .accessibilityLabel(Self.spoken(status, elapsed: meeting.elapsed()))
                    .accessibilityHint("Opens the meeting's page")
                if status.live {
                    CapsuleIconButton(symbol: status.phase == .paused ? "play.fill" : "pause.fill",
                                      label: status.phase == .paused ? "Go on" : "Pause") {
                        meeting.pause(status.phase != .paused)
                    }
                    StopButton { meeting.stop() }
                }
            }
            .padding(.leading, 11)
            .padding(.trailing, status.live ? 5 : 12)
            .padding(.vertical, 5)
            .frame(minHeight: 34)
            .floatingSurface(Capsule(style: .continuous),
                             edge: status.phase == .recording ? MeetingColors.live.opacity(0.45) : nil)
            .padding(.trailing, Surface.trailingInset)
            .transition(reduceMotion ? .opacity : .asymmetric(
                insertion: .scale(scale: 0.6, anchor: .bottomTrailing).combined(with: .opacity),
                removal: .scale(scale: 0.85, anchor: .bottomTrailing).combined(with: .opacity)))
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Meeting notes")
        }
    }

    @ViewBuilder private func label(_ status: MeetingStatus) -> some View {
        HStack(spacing: 7) {
            switch status.phase {
            case .writing:
                ThinkingDots(color: theme.primary).frame(width: 30)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Writing your notes")
                        .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.ink.opacity(0.9))
                    if !status.step.isEmpty {
                        Text(status.step)
                            .font(.system(size: 11))
                            .foregroundStyle(theme.ink.opacity(0.6))
                            .transition(.opacity)
                            .id(status.step)
                    }
                }
                .fixedSize()
            default:
                if status.error.isEmpty {
                    LiveLight(paused: status.phase == .paused)
                } else {
                    // Something can't be heard: the light turns into a warning, the bubble says what and how to fix it.
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(theme.accent)
                        .frame(width: 16, height: 16)
                        .help(status.error)
                        .accessibilityLabel(status.error)
                }
                Text(status.phase == .paused ? "Paused" : "Taking notes")
                    .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.9))
                    .fixedSize()
                // Ticks once a second, only while it counts.
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    Text(MeetingModel.clock(meeting.elapsed()))
                        .font(.system(size: 12.5, weight: .medium, design: .rounded).monospacedDigit())
                        .foregroundStyle(theme.ink.opacity(0.6))
                        .fixedSize()
                }
            }
        }
        .contentShape(Rectangle())
    }

    /// What VoiceOver says for the capsule: "Taking notes, 12 minutes".
    static func spoken(_ status: MeetingStatus, elapsed: TimeInterval) -> String {
        switch status.phase {
        case .writing: return "Writing your notes. \(status.step)"
        case .paused: return "Meeting notes paused at \(MeetingModel.length(elapsed))"
        default: return "Taking notes, \(MeetingModel.length(elapsed)) so far"
        }
    }
}

/// The colours meeting notes wear: the red of a recording light, and its grey when paused.
enum MeetingColors {
    static let live = Color(red: 0.89, green: 0.27, blue: 0.27)
    /// Speakers in a transcript, in turn: Milo's lavender family and warm colours that read on his paper.
    static func speaker(_ index: Int, _ theme: Theme) -> Color {
        let palette: [Color] = [
            Color(red: 0.80, green: 0.42, blue: 0.20),
            Color(red: 0.16, green: 0.55, blue: 0.52),
            Color(red: 0.76, green: 0.29, blue: 0.47),
            Color(red: 0.33, green: 0.47, blue: 0.80),
            Color(red: 0.50, green: 0.55, blue: 0.20),
        ]
        return palette[index % palette.count]
    }
}

/// The recording light: red and breathing slowly while it records, a grey bar pair while paused.
struct LiveLight: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var paused: Bool

    var body: some View {
        ZStack {
            if paused {
                Image(systemName: "pause.circle.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(theme.ink.opacity(0.45))
            } else {
                TimelineView(.animation(minimumInterval: 1 / 15, paused: reduceMotion)) { context in
                    let t = context.date.timeIntervalSinceReferenceDate
                    let glow = reduceMotion ? 0.5 : 0.5 + 0.5 * sin(t * 2 * .pi / 1.8)
                    Circle()
                        .fill(MeetingColors.live)
                        .frame(width: 9, height: 9)
                        .background(Circle().fill(MeetingColors.live.opacity(0.18 + 0.2 * glow)).frame(width: 16, height: 16))
                }
            }
        }
        .frame(width: 16, height: 16)
        .accessibilityHidden(true)
    }
}

/// A small round button in the capsule: Pause, Go on.
struct CapsuleIconButton: View {
    @Environment(\.miloTheme) private var theme
    let symbol: String
    let label: String
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 10.5, weight: .bold))
                .foregroundStyle(theme.ink.opacity(0.75))
                .frame(width: 24, height: 24)
                .background(Circle().fill(theme.primary.opacity(hover ? 0.16 : 0.09)))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .help(label)
        .accessibilityLabel(label)
    }
}

/// "Stop": the one button to end the notes, filled so it is the first thing the eye finds.
struct StopButton: View {
    @Environment(\.miloTheme) private var theme
    var compact = true
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                    .fill(theme.onPrimary)
                    .frame(width: compact ? 7 : 8, height: compact ? 7 : 8)
                Text("Stop")
                    .font(.system(size: compact ? 12 : 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.onPrimary)
            }
            .fixedSize()
            .padding(.horizontal, compact ? 10 : 14)
            .frame(height: compact ? 24 : 30)
            .background(Capsule(style: .continuous).fill(theme.primary.opacity(hover ? 0.88 : 1)))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
        .help("Stop taking notes and write them up")
        .accessibilityLabel("Stop taking notes")
    }
}
