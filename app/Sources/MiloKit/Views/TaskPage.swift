import SwiftUI

/// A task in the chat: one compact card with what it is, how it's going and how many steps. A click opens its page.
struct TaskCard: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let entry: TranscriptEntry
    var helper: HelperInfo?
    /// Its Undo, once it changed something and has finished (ADR 0024).
    var undo: UndoPoint?
    var undoTask: (String) -> Void = { _ in }
    let open: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: open) {
            HStack(alignment: .center, spacing: 11) {
                StatusSeal(status: entry.status, needsYou: helper?.status == .needsYou)
                VStack(alignment: .leading, spacing: 3) {
                    Text(entry.headline)
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.ink)
                        .lineLimit(1)
                    Text(line)
                        .font(.system(size: 11.5))
                        .foregroundStyle(entry.status == .failed ? WindowColors.failed : theme.ink.opacity(0.58))
                        .lineLimit(1)
                    if entry.status == .running {
                        ProgressLine(progress: helper?.progress, status: helper?.status ?? .working)
                            .frame(height: 3)
                            .padding(.top, 3)
                    }
                }
                Spacer(minLength: 6)
                if undo != nil { Color.clear.frame(width: Self.undoRoom, height: 1) }
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(theme.ink.opacity(hovered ? 0.6 : 0.3))
                    .offset(x: hovered && !reduceMotion ? 2 : 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(theme.card))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(hovered ? theme.primary.opacity(0.35) : theme.rule, lineWidth: 1))
            .shadow(color: theme.primary.opacity(hovered ? 0.12 : 0.05), radius: hovered ? 8 : 4, y: 2)
            .scaleEffect(hovered && !reduceMotion ? 1.005 : 1)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        // Over the card, not in it: a button inside the card's own button would open the task instead.
        .overlay(alignment: .trailing) {
            if let undo { UndoButton(point: undo, undo: undoTask).padding(.trailing, 30) }
        }
        .onHover { hovered = $0 }
        .animation(theme.motion.animation(reduced: reduceMotion), value: hovered)
        .help("Open this task")
        .accessibilityLabel("Task: \(entry.headline), \(Self.statusWords(entry.status))")
        .accessibilityHint("Opens its steps and result")
    }

    private var line: String {
        let steps = entry.steps.count == 1 ? "1 step" : "\(entry.steps.count) steps"
        switch entry.status {
        case .running:
            if let step = helper?.step, !step.isEmpty { return step }
            return entry.steps.last.map { "\($0.title) · \(steps)" } ?? "Starting…"
        case .done:
            let result = entry.result.split(separator: "\n").first.map(String.init) ?? ""
            return result.isEmpty ? "Done · \(steps)" : result
        case .failed:
            return entry.result.isEmpty ? "Couldn't finish" : entry.result
        }
    }

    /// Room kept on the card for the Undo laid over it.
    static let undoRoom: CGFloat = 76

    static func statusWords(_ status: ActivityStep.Status) -> String {
        switch status {
        case .running: "working on it"
        case .done: "done"
        case .failed: "couldn't finish"
        }
    }
}

/// A task's status as a small seal: a ring that turns while it works, a check when done, a cross when it failed.
struct StatusSeal: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let status: ActivityStep.Status
    var needsYou = false
    var size: CGFloat = 26
    @State private var turn = false

    var body: some View {
        ZStack {
            Circle().fill(color.opacity(0.14))
            switch status {
            case .running:
                Circle()
                    .trim(from: 0, to: 0.7)
                    .stroke(color, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    .padding(5)
                    .rotationEffect(.degrees(turn ? 360 : 0))
                if needsYou {
                    Text("?").font(.system(size: size * 0.42, weight: .heavy, design: .rounded)).foregroundStyle(color)
                }
            case .done:
                Image(systemName: "checkmark").font(.system(size: size * 0.38, weight: .heavy)).foregroundStyle(color)
            case .failed:
                Image(systemName: "xmark").font(.system(size: size * 0.34, weight: .heavy)).foregroundStyle(color)
            }
        }
        .frame(width: size, height: size)
        .onAppear {
            guard status == .running, !reduceMotion else { return }
            withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) { turn = true }
        }
        .accessibilityHidden(true)
    }

    private var color: Color {
        switch status {
        case .running: needsYou ? Palette.think : WindowColors.running
        case .done: WindowColors.done
        case .failed: WindowColors.failed
        }
    }
}

/// A task's own page: what it is, how it went, every step, the result and the files it touched.
struct TaskPage: View {
    @Environment(\.miloTheme) private var theme
    let entry: TranscriptEntry
    let conversation: ConversationInfo?
    var helper: HelperInfo?
    var undo: UndoPoint?
    var undoTask: (String) -> Void = { _ in }
    let openConversation: (String) -> Void
    let stop: (String) -> Void
    let reveal: (String) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                if !entry.result.isEmpty && entry.status != .running { result }
                if !entry.files.isEmpty { files }
                steps
            }
            .padding(.horizontal, 26)
            .padding(.top, 20)
            .padding(.bottom, 28)
            .frame(maxWidth: 640, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let conversation {
                Button { openConversation(conversation.id) } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "bubble.left").font(.system(size: 10, weight: .semibold))
                        Text("Asked in “\(conversation.title)”").lineLimit(1)
                        Image(systemName: "arrow.up.forward").font(.system(size: 8.5, weight: .bold))
                    }
                    .font(.system(size: 11.5, weight: .medium, design: .rounded))
                    .foregroundStyle(theme.primary)
                }
                .buttonStyle(.plain)
                .help("Open the conversation this task came from")
            }
            HStack(alignment: .center, spacing: 12) {
                StatusSeal(status: entry.status, needsYou: helper?.status == .needsYou, size: 34)
                VStack(alignment: .leading, spacing: 3) {
                    Text(entry.headline)
                        .font(.system(size: 19, weight: .bold, design: .rounded))
                        .foregroundStyle(theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 6) {
                        StatusPill(status: entry.status, needsYou: helper?.status == .needsYou)
                        Text(when)
                            .font(.system(size: 11.5).monospacedDigit())
                            .foregroundStyle(theme.ink.opacity(0.5))
                    }
                }
                Spacer(minLength: 8)
                if entry.status == .running {
                    Button("Stop") { stop(entry.id) }
                        .buttonStyle(StopButtonStyle())
                        .help("Stop this helper")
                } else if let undo {
                    UndoButton(point: undo, undo: undoTask)
                }
            }
            if entry.text != entry.headline {
                Text(entry.text)
                    .font(.system(size: 12.5))
                    .foregroundStyle(theme.ink.opacity(0.65))
                    .lineSpacing(2)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if entry.status == .running, let helper {
                VStack(alignment: .leading, spacing: 5) {
                    if !helper.step.isEmpty {
                        Text(helper.step).font(.system(size: 12, weight: .medium)).foregroundStyle(theme.ink.opacity(0.75))
                    }
                    ProgressLine(progress: helper.progress, status: helper.status).frame(height: 4)
                }
                .padding(.top, 2)
            }
        }
    }

    private var result: some View {
        HStack(alignment: .top, spacing: 10) {
            Text(entry.result)
                .font(.system(size: 14, design: .rounded))
                .foregroundStyle(theme.ink)
                .lineSpacing(2.5)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 14)
        .padding(.leading, 18)
        .padding(.trailing, 14)
        .background(theme.card)
        .overlay(alignment: .leading) { Rectangle().fill(WindowColors.status(entry.status)).frame(width: 4) }
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Milo reported: \(entry.result)")
    }

    private var files: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionLabel(text: entry.files.count == 1 ? "1 file" : "\(entry.files.count) files")
            VStack(spacing: 0) {
                ForEach(Array(entry.files.enumerated()), id: \.element) { i, path in
                    FileRow(path: path, reveal: { reveal(path) })
                    if i < entry.files.count - 1 { Rectangle().fill(theme.rule).frame(height: 1).padding(.leading, 40) }
                }
            }
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(theme.card))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
        }
    }

    @ViewBuilder private var steps: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionLabel(text: entry.steps.isEmpty ? "No steps yet" : entry.steps.count == 1 ? "1 step" : "\(entry.steps.count) steps")
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(entry.steps.enumerated()), id: \.element.id) { i, step in
                    StepRow(step: step, last: i == entry.steps.count - 1, showDetail: TaskBlock.openDetails.contains(step.id))
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
            }
        }
    }

    private var when: String {
        let time = entry.date.formatted(date: .omitted, time: .shortened)
        let day = DayGroups.heading(entry.date, now: ConversationsSidebar.now())
        return day == "Today" ? "Today at \(time)" : "\(day == "Yesterday" ? "Yesterday" : entry.date.formatted(.dateTime.weekday(.wide).day().month(.wide))) at \(time)"
    }
}

/// "Working on it", "Done", "Couldn't finish" in the status colour.
struct StatusPill: View {
    let status: ActivityStep.Status
    var needsYou = false

    var body: some View {
        Text(needsYou ? "Waiting for you" : TaskPage.headline(status))
            .font(.system(size: 10.5, weight: .bold, design: .rounded))
            .foregroundStyle(color)
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(Capsule().fill(color.opacity(0.13)))
    }

    private var color: Color { needsYou ? Palette.think : WindowColors.status(status) }
}

extension TaskPage {
    static func headline(_ status: ActivityStep.Status) -> String {
        switch status {
        case .running: "Working on it"
        case .done: "Done"
        case .failed: "Couldn't finish"
        }
    }
}

/// A file a task named: its icon, its name, its folder, and Show in Finder.
struct FileRow: View {
    @Environment(\.miloTheme) private var theme
    let path: String
    let reveal: () -> Void
    @State private var hovered = false

    var body: some View {
        HStack(spacing: 10) {
            Image(nsImage: NSWorkspace.shared.icon(forFile: (path as NSString).expandingTildeInPath))
                .resizable()
                .frame(width: 22, height: 22)
            VStack(alignment: .leading, spacing: 1) {
                Text((path as NSString).lastPathComponent)
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundStyle(theme.ink)
                    .lineLimit(1)
                Text(Self.folder(path))
                    .font(.system(size: 11))
                    .foregroundStyle(theme.ink.opacity(0.5))
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            Spacer(minLength: 8)
            Button("Show in Finder", action: reveal)
                .buttonStyle(PillButtonStyle(prominent: false))
                .controlSize(.small)
                .opacity(hovered ? 1 : 0.75)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .onHover { hovered = $0 }
    }

    /// "in Reports" for ~/Reports/x.numbers.
    static func folder(_ path: String) -> String {
        let folder = (path as NSString).deletingLastPathComponent
        let name = (folder as NSString).lastPathComponent
        return folder == "~" ? "in your home folder" : "in \(name)"
    }
}

struct SectionLabel: View {
    @Environment(\.miloTheme) private var theme
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(.system(size: 10, weight: .bold, design: .rounded))
            .tracking(0.8)
            .foregroundStyle(theme.ink.opacity(0.45))
    }
}

struct StopButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(WindowColors.failed)
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(WindowColors.failed.opacity(0.6), lineWidth: 1))
            .scaleEffect(configuration.isPressed ? 0.95 : 1)
    }
}
