import SwiftUI

/// Work Milo handed to his helper: a header, the steps hanging on a thread, then what he reported.
/// Open while it runs or failed, folded once it is done; a click on the header toggles it.
struct TaskBlock: View {
    @Environment(\.miloTheme) private var theme
    let entry: TranscriptEntry
    @State private var expanded: Bool?
    /// Step ids whose detail starts open. For offscreen renders.
    static var openDetails: Set<String> = []

    private var isOpen: Bool { expanded ?? (entry.status != .done) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { expanded = !isOpen } label: { header }
                .buttonStyle(.plain)
                .accessibilityHint(isOpen ? "Hides the steps" : "Shows the steps")
            if isOpen && !entry.steps.isEmpty {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(entry.steps.enumerated()), id: \.element.id) { i, step in
                        StepRow(step: step, last: i == entry.steps.count - 1,
                                showDetail: Self.openDetails.contains(step.id))
                    }
                }
                .padding(.top, 6)
                .transition(.opacity)
            }
            if entry.status != .running, !entry.result.isEmpty {
                MiloLine(text: entry.result, emotion: entry.status == .failed ? .confused : .happy)
                    .padding(.top, 8)
                    .padding(.leading, -19)  // Milo's dot sits in the same column as in his other lines
            }
        }
        .padding(.leading, 19)
        .animation(.easeOut(duration: 0.18), value: isOpen)
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            VStack(alignment: .leading, spacing: 2) {
                Text(headline)
                    .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                    .foregroundStyle(entry.status == .failed ? WindowColors.failed : Color.primary)
                Text(entry.text)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(isOpen ? 4 : 1)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: 8)
            if !entry.steps.isEmpty {
                Text(entry.steps.count == 1 ? "1 step" : "\(entry.steps.count) steps")
                    .font(.system(size: 11).monospacedDigit())
                    .foregroundStyle(.tertiary)
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .rotationEffect(.degrees(isOpen ? 90 : 0))
            }
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(theme.ink.opacity(0.05)))
        .overlay(alignment: .leading) {
            UnevenRoundedRectangle(topLeadingRadius: 9, bottomLeadingRadius: 9, style: .continuous)
                .fill(WindowColors.status(entry.status))
                .frame(width: 3)
        }
        .contentShape(Rectangle())
    }

    private var headline: String {
        switch entry.status {
        case .running: "Working on it"
        case .done: "Done"
        case .failed: "Couldn't finish"
        }
    }
}

/// One step: a bead on the thread, what Milo did in plain words, and the raw detail on request.
struct StepRow: View {
    @Environment(\.miloTheme) private var theme
    let step: ActivityStep
    let last: Bool
    @State private var showDetail: Bool

    init(step: ActivityStep, last: Bool, showDetail: Bool = false) {
        self.step = step
        self.last = last
        _showDetail = State(initialValue: showDetail)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Bead(status: step.status)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 5) {
                Button { showDetail.toggle() } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Image(systemName: Self.icon(step.kind))
                            .font(.system(size: 10.5))
                            .foregroundStyle(.secondary)
                            .frame(width: 14)
                        Text(step.title)
                            .font(.system(size: 12.5))
                            .foregroundStyle(step.status == .failed ? WindowColors.failed : Color.primary)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(step.detail.isEmpty)
                .help(step.detail.isEmpty ? "" : "Show what exactly Milo ran")
                if showDetail && !step.detail.isEmpty {
                    Text(step.detail)
                        .font(.system(size: 10.5, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .lineLimit(12)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 6, style: .continuous).fill(theme.ink.opacity(0.05)))
                }
            }
            .padding(.bottom, last ? 0 : 9)
        }
        .background(alignment: .topLeading) {
            if !last {
                Rectangle().fill(theme.primary.opacity(0.25)).frame(width: 1.5)
                    .padding(.top, 18).padding(.leading, 6.25)
            }
        }
        .padding(.leading, 3)
        .accessibilityElement(children: .combine)
        .accessibilityValue(step.status.rawValue)
    }

    static func icon(_ kind: String) -> String {
        switch kind {
        case "command": "terminal"
        case "read": "doc.text"
        case "edit": "pencil"
        case "search": "magnifyingglass"
        case "web": "globe"
        case "app": "macwindow"
        case "tool": "wrench.and.screwdriver"
        default: "sparkle"
        }
    }
}

/// Running: an amber ring that breathes. Done: a filled dot with a check. Failed: a cross.
struct Bead: View {
    let status: ActivityStep.Status
    @State private var breathe = false

    var body: some View {
        ZStack {
            switch status {
            case .running:
                Circle().strokeBorder(WindowColors.running, lineWidth: 1.5)
                Circle().fill(WindowColors.running).padding(4)
                    .scaleEffect(breathe ? 1 : 0.55)
                    .animation(.easeInOut(duration: 0.8).repeatForever(), value: breathe)
                    .onAppear { breathe = true }
            case .done:
                Circle().fill(WindowColors.done)
                Image(systemName: "checkmark").font(.system(size: 7, weight: .heavy)).foregroundStyle(.white)
            case .failed:
                Circle().fill(WindowColors.failed)
                Image(systemName: "xmark").font(.system(size: 6.5, weight: .heavy)).foregroundStyle(.white)
            }
        }
        .frame(width: 14, height: 14)
    }
}
