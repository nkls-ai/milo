import SwiftUI

/// One conversation: its title, its lines with each task as a card, and the field to go on with it. The one going
/// on also shows Milo's waiting question and recipe draft. Typing in an older one picks it up again.
struct ConversationPage: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var transcript: TranscriptModel
    @ObservedObject var model: MiloModel
    @ObservedObject var settings: ConversationSettings
    @ObservedObject var route: WindowRoute
    /// "" while no conversation has started yet.
    let id: String
    let actions: WindowActions
    @AppStorage("speakTypedReplies") private var speakReplies = false

    private var live: Bool { id.isEmpty || id == transcript.current }
    private var entries: [TranscriptEntry] { transcript.entries(of: id) }
    private var info: ConversationInfo? { id.isEmpty ? nil : transcript.info(id) }

    var body: some View {
        VStack(spacing: 0) {
            if let info { ConversationHeader(info: info, live: live, rename: { actions.rename(info.id, $0) }) }
            if entries.isEmpty && (!live || model.state == .idle) {
                if live {
                    EmptyConversation(talkKey: settings.talkKey)
                } else {
                    Opening()
                }
            } else {
                scroll
            }
            if live, let draft = model.drafts.last {
                DraftCard(draft: draft, talkKey: settings.talkKey,
                          save: { model.answerDraft(draft.id, save: true) },
                          change: { settings.prefill = "Change \(draft.name): " },
                          drop: { model.answerDraft(draft.id, save: false) })
            }
            if live, let question = model.question {
                QuestionBar(question: question, talkKey: settings.talkKey, answer: { model.answer($0) })
            }
            InputBar(speakReplies: $speakReplies, prefill: $settings.prefill,
                     placeholder: live ? "Type to Milo" : "Continue this conversation", focusTick: settings.typeHere) {
                actions.send($0, speakReplies, live ? "" : id)
            }
        }
    }

    private var scroll: some View {
        ScrollViewReader { proxy in
            ScrollView {
                TranscriptList(entries: entries, state: live ? model.state : .idle, helpers: model.helpers,
                               openTask: { route.go(.task($0)) })
                    .padding(.horizontal, 18)
                    .padding(.top, 14)
                    .padding(.bottom, 10)
                Color.clear.frame(height: 1).id(Self.bottom)
            }
            .onAppear { proxy.scrollTo(Self.bottom, anchor: .bottom) }
            .onChange(of: scrollKey) { proxy.scrollTo(Self.bottom, anchor: .bottom) }
        }
    }

    private static let bottom = "bottom"

    /// Changes whenever something new appears at the end, so the list follows it.
    private var scrollKey: String {
        let last = entries.last
        return "\(id)-\(entries.count)-\(last?.text.count ?? 0)-\(last?.steps.count ?? 0)-\(model.state)"
    }
}

/// A conversation's title, what kind it is and when, the title renamable with a double click.
struct ConversationHeader: View {
    @Environment(\.miloTheme) private var theme
    let info: ConversationInfo
    let live: Bool
    let rename: (String) -> Void
    @State private var editing = false
    @State private var name = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 11) {
            Image(systemName: Self.icon(info))
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(info.kind == .chat && !info.fromPhone ? theme.primary : theme.accent)
                .frame(width: 30, height: 30)
                .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill((info.kind == .chat && !info.fromPhone ? theme.primary : theme.accent).opacity(0.13)))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                if editing {
                    TextField("Name", text: $name)
                        .textFieldStyle(.plain)
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .focused($focused)
                        .onSubmit(save)
                        .onExitCommand { editing = false }
                        .onChange(of: focused) { if !focused { save() } }
                } else {
                    Text(info.title)
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                        .foregroundStyle(theme.ink)
                        .lineLimit(1)
                        .onTapGesture(count: 2) { start() }
                        .help("Double-click to rename")
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityAction(named: "Rename") { start() }
                }
                Text(Self.subtitle(info, now: ConversationsSidebar.now()))
                    .font(.system(size: 11))
                    .foregroundStyle(theme.ink.opacity(0.5))
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            if live {
                HStack(spacing: 6) {
                    ThreadBead(state: .live)
                    Text("Going on")
                        .font(.system(size: 10.5, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.primary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Capsule().fill(theme.primary.opacity(0.1)))
                .help("Milo is in this conversation now: what you say next goes on here")
            }
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 11)
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }

    private func start() {
        name = info.title
        editing = true
        focused = true
    }

    private func save() {
        guard editing else { return }
        editing = false
        let title = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if !title.isEmpty && title != info.title { rename(title) }
    }

    static func icon(_ info: ConversationInfo) -> String {
        switch info.kind {
        case .meeting: "person.2.wave.2.fill"
        case .routine: "arrow.triangle.2.circlepath"
        case .chat: info.fromPhone ? "iphone" : "bubble.left.and.bubble.right.fill"
        }
    }

    /// "Today 9:12 · 6 turns · 1 task · from your phone".
    static func subtitle(_ info: ConversationInfo, now: Date) -> String {
        var parts: [String] = []
        let day = DayGroups.heading(info.started, now: now)
        let time = info.started.formatted(date: .omitted, time: .shortened)
        switch day {
        case "Today", "Yesterday": parts.append("\(day) \(time)")
        default: parts.append(info.started.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated)) + " \(time)")
        }
        switch info.kind {
        case .meeting: parts.append("meeting notes")
        case .routine: parts.append("routine run")
        case .chat: if info.turns > 0 { parts.append(info.turns == 1 ? "1 turn" : "\(info.turns) turns") }
        }
        if !info.tasks.isEmpty { parts.append(info.tasks.count == 1 ? "1 task" : "\(info.tasks.count) tasks") }
        if info.fromPhone { parts.append("from your phone") }
        return parts.joined(separator: " · ")
    }
}

/// While an older conversation's lines are on their way.
private struct Opening: View {
    @Environment(\.miloTheme) private var theme

    var body: some View {
        VStack(spacing: 10) {
            ThinkingDots(color: theme.accent).scaleEffect(0.7)
            Text("Opening…").font(.system(size: 12)).foregroundStyle(theme.ink.opacity(0.5))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A task the window hasn't loaded yet, or one that is gone.
struct TaskMissing: View {
    @Environment(\.miloTheme) private var theme
    let loading: Bool
    let back: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            if loading {
                ThinkingDots(color: theme.accent).scaleEffect(0.7)
                Text("Opening the task…").font(.system(size: 12)).foregroundStyle(theme.ink.opacity(0.5))
            } else {
                Image(systemName: "questionmark.folder").font(.system(size: 22)).foregroundStyle(theme.primary.opacity(0.6))
                Text("Milo can't find this task any more.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.75))
                Button("Go back", action: back).buttonStyle(.plain).foregroundStyle(theme.primary)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
