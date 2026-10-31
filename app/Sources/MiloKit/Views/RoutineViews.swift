import SwiftUI

/// The Routines section at the top of the Milo window: a line that opens into the user's routines, each with
/// its schedule, its last run and Run now. Closed, it takes one line; the conversation keeps the window.
struct RoutinesPanel: View {
    @Environment(\.miloTheme) private var theme
    let routines: [RoutineInfo]
    @Binding var open: Bool
    let act: (String, RoutineAction) -> Void
    /// Rows shown before the list scrolls.
    static let rows = 4

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { withAnimation(theme.motion.spring) { open.toggle() } } label: {
                HStack(spacing: 6) {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 9, weight: .bold))
                        .rotationEffect(.degrees(open ? 90 : 0))
                    Text(routines.count == 1 ? "1 routine" : "\(routines.count) routines")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                    if !open, let next = Self.nextUp(routines) {
                        Text("· next: \(next.name), \(Self.when(next.nextRun!))")
                            .font(.system(size: 11))
                            .lineLimit(1)
                    }
                    Spacer()
                }
                .foregroundStyle(.secondary)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(open ? "Hide your routines" : "Show your routines")
            .accessibilityLabel("Routines")
            .accessibilityValue(open ? "shown" : "hidden")
            if open {
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(routines) { routine in
                            RoutineRow(routine: routine, act: { act(routine.id, $0) })
                        }
                    }
                }
                .frame(maxHeight: CGFloat(Self.rows) * 52)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(theme.ink.opacity(0.05))
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }

    /// The routine whose schedule comes up first.
    static func nextUp(_ routines: [RoutineInfo]) -> RoutineInfo? {
        routines.filter { $0.nextRun != nil && !$0.paused }.min { $0.nextRun! < $1.nextRun! }
    }

    /// "today at 09:00", "tomorrow at 09:00", "Monday at 09:00", "on 2 Nov at 09:00".
    static func when(_ date: Date, now: Date = Date(), calendar: Calendar = .current) -> String {
        let time = date.formatted(date: .omitted, time: .shortened)
        if calendar.isDate(date, inSameDayAs: now) { return "today at \(time)" }
        if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(date, inSameDayAs: tomorrow) {
            return "tomorrow at \(time)"
        }
        if let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now),
                                              to: calendar.startOfDay(for: date)).day, days < 7 {
            return "\(date.formatted(.dateTime.weekday(.wide))) at \(time)"
        }
        return "on \(date.formatted(.dateTime.day().month(.abbreviated))) at \(time)"
    }
}

struct RoutineRow: View {
    @Environment(\.miloTheme) private var theme
    let routine: RoutineInfo
    let act: (RoutineAction) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: routine.problem != nil ? "exclamationmark.triangle" :
                    routine.paused ? "pause.circle" : routine.schedule.isEmpty ? "list.bullet.rectangle" : "clock")
                .font(.system(size: 13))
                .foregroundStyle(routine.problem != nil ? WindowColors.failed : theme.primary)
                .frame(width: 18)
                .padding(.top, 1)
            VStack(alignment: .leading, spacing: 2) {
                Text(routine.name)
                    .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                    .lineLimit(1)
                Text(Self.summary(routine))
                    .font(.system(size: 11))
                    .foregroundStyle(routine.problem != nil ? WindowColors.failed : Color.secondary)
                    .lineLimit(2)
                    .help(routine.description)
            }
            Spacer(minLength: 0)
            if routine.problem == nil {
                Button { act(.run) } label: {
                    Text("Run now")
                        .font(.system(size: 11.5, weight: .medium))
                        .padding(.horizontal, 9)
                        .padding(.vertical, 4)
                        .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(theme.primary.opacity(0.55), lineWidth: 1))
                        .foregroundStyle(theme.primary)
                }
                .buttonStyle(.plain)
                .help(routine.inputs.isEmpty ? "Do it now" : "Do it now with the usual \(routine.inputs.joined(separator: ", "))")
                .accessibilityLabel("Run \(routine.name) now")
                Menu {
                    if !routine.schedule.isEmpty {
                        Button(routine.paused ? "Resume the schedule" : "Pause the schedule") {
                            act(routine.paused ? .resume : .pause)
                        }
                    }
                    Button("Delete", role: .destructive) { act(.delete) }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 12, weight: .medium))
                        .frame(width: 20, height: 22)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                .accessibilityLabel("More for \(routine.name)")
            }
        }
    }

    /// "Every Monday at 09:00 · last run 26 Oct, done", "Paused", "Only when you ask".
    static func summary(_ routine: RoutineInfo) -> String {
        if let problem = routine.problem { return problem }
        var parts: [String] = []
        if routine.schedule.isEmpty {
            parts.append("Only when you ask")
        } else {
            parts.append(routine.schedule.prefix(1).uppercased() + routine.schedule.dropFirst()
                         + (routine.paused ? ", paused" : ""))
        }
        if !routine.lastRun.isEmpty { parts.append("last run \(lastRun(routine.lastRun))") }
        return parts.joined(separator: " · ")
    }

    /// "2026-10-26 09:00, done" as "Oct 26 at 09:00, done" in the user's locale; anything else as it is.
    static func lastRun(_ text: String) -> String {
        let parts = text.split(separator: ",", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd HH:mm"
        guard let date = f.date(from: parts[0]) else { return text }
        let when = date.formatted(.dateTime.day().month(.abbreviated).hour().minute())
        return parts.count > 1 ? "\(when), \(parts[1])" : when
    }
}

/// A recipe Milo wrote down, waiting for the user's look: its steps and inputs, Save, Change it, and a way to
/// throw it away. Pinned above the text field, like a question.
struct DraftCard: View {
    @Environment(\.miloTheme) private var theme
    let draft: RoutineDraft
    let talkKey: String
    let save: () -> Void
    let change: () -> Void
    let drop: () -> Void
    /// Shows the file exactly as Save writes it, front matter and all.
    @State private var whole = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("New routine: \(draft.name)")
                        .font(.system(size: 13.5, weight: .semibold, design: .rounded))
                    Text(draft.schedule.isEmpty ? "Runs when you ask for it." : "Runs \(draft.schedule).")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button(action: drop) {
                    Image(systemName: "xmark").font(.system(size: 10, weight: .semibold)).frame(width: 18, height: 18)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Throw this recipe away")
                .accessibilityLabel("Throw away")
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    if whole {
                        Text(draft.recipe)
                            .font(.system(size: 11, design: .monospaced))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    if !whole && !draft.inputs.isEmpty {
                        Text("Each time: " + draft.inputs.joined(separator: "; "))
                            .font(.system(size: 11.5, weight: .medium))
                            .foregroundStyle(theme.primary)
                    }
                    if !whole && !draft.apps.isEmpty {
                        Text("Uses the screen with " + draft.apps.joined(separator: ", "))
                            .font(.system(size: 11.5, weight: .medium))
                            .foregroundStyle(theme.primary)
                    }
                    if !whole { ForEach(Array(Self.lines(draft.steps).enumerated()), id: \.offset) { _, line in
                        Text(line.text)
                            .font(.system(size: line.heading ? 12.5 : 12, weight: line.heading ? .semibold : .regular,
                                          design: line.heading ? .rounded : .default))
                            .padding(.top, line.heading ? 4 : 0)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } }
                }
                .padding(10)
            }
            .frame(maxHeight: 190)
            .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(theme.card))
            HStack(spacing: 8) {
                Button(whole ? "Show the steps" : "Show the whole file") { whole.toggle() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .help("The file exactly as Save keeps it")
                Spacer()
                Button("Change it", action: change)
                    .help("Type what to change, or hold \(talkKey) and say it")
                    .buttonStyle(.plain)
                    .font(.system(size: 12, weight: .medium))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                        .strokeBorder(theme.rule, lineWidth: 1))
                Button("Save", action: save)
                    .buttonStyle(.plain)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(theme.onPrimary)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(theme.primary))
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(theme.ink.opacity(0.05))
        .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Milo wrote down \(draft.name)")
    }

    /// The recipe's lines for reading: "## Steps" becomes a heading, blank lines go.
    static func lines(_ text: String) -> [(text: String, heading: Bool)] {
        text.components(separatedBy: "\n").compactMap { line in
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { return nil }
            if trimmed.hasPrefix("#") {
                return (trimmed.drop(while: { $0 == "#" }).trimmingCharacters(in: .whitespaces), true)
            }
            return (line.hasPrefix("   ") ? "    " + trimmed : trimmed, false)
        }
    }
}
