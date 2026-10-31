import AppKit
import SwiftUI

/// What the Milo window needs besides the transcript: the talk key's name for the empty state.
public final class ConversationSettings: ObservableObject {
    @Published public var talkKey: String
    /// The task to open, set when the user clicks a helper.
    @Published public var focus: String?
    /// Text to put in the field, ready to finish and send: "Change it" on a recipe draft.
    @Published public var prefill: String?
    /// Bumped to put the cursor in the text field (⌘L).
    @Published public var typeHere = 0

    public init(talkKey: String) {
        self.talkKey = talkKey
    }
}

/// The Milo window: the conversations down the side, and Today, a conversation or a task beside them.
/// See docs/design/conversations.md.
public struct ConversationView: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var transcript: TranscriptModel
    @ObservedObject var model: MiloModel
    @ObservedObject var settings: ConversationSettings
    @ObservedObject var route: WindowRoute
    let actions: WindowActions
    @ObservedObject var usage: UsageModel
    @FocusState private var searching: Bool
    @AppStorage("speakTypedReplies") private var speakReplies = false
    @State private var pendingSearch: Task<Void, Never>?
    /// Below this width the sidebar folds away and ⌘0 brings it over the page.
    static let narrow: CGFloat = 600
    static let sidebarWidth: CGFloat = 236

    public init(transcript: TranscriptModel, model: MiloModel, settings: ConversationSettings, route: WindowRoute,
                actions: WindowActions, usage: UsageModel = UsageModel()) {
        self.transcript = transcript
        self.model = model
        self.settings = settings
        self.route = route
        self.actions = actions
        self.usage = usage
    }

    /// Just the conversation going on, for the narrow window of old and for tests.
    public init(transcript: TranscriptModel, model: MiloModel, settings: ConversationSettings,
                send: @escaping (_ text: String, _ speak: Bool) -> Void) {
        self.init(transcript: transcript, model: model, settings: settings, route: WindowRoute(page: .live),
                  actions: WindowActions(send: { text, speak, _ in send(text, speak) }))
    }

    public var body: some View {
        GeometryReader { geometry in
            let narrow = geometry.size.width < Self.narrow
            HStack(spacing: 0) {
                if !narrow {
                    sidebar
                    Rectangle().fill(theme.rule).frame(width: 1)
                }
                pages(narrow: narrow)
            }
            .overlay(alignment: .leading) {
                if narrow && route.sidebarShown {
                    ZStack(alignment: .leading) {
                        Color.black.opacity(0.18)
                            .onTapGesture { route.sidebarShown = false }
                            .transition(.opacity)
                        sidebar
                            .shadow(color: .black.opacity(0.18), radius: 16, x: 4)
                            .transition(.move(edge: .leading))
                    }
                }
            }
            .animation(theme.motion.animation(reduced: reduceMotion), value: route.sidebarShown)
        }
        .background(theme.tint)
        .background(shortcuts)
        .onChange(of: settings.focus) {
            guard let id = settings.focus else { return }
            settings.focus = nil
            if transcript.task(id) == nil, let conversation = transcript.conversation(ofTask: id) {
                actions.open(conversation.id)
            }
            route.go(.task(id))
        }
        .onChange(of: route.search) { searchChanged() }
        .onChange(of: route.page) { route.sidebarShown = false }
    }

    private var sidebar: some View {
        ConversationsSidebar(transcript: transcript, route: route, waiting: waiting, actions: actions,
                             searchFocus: $searching, meeting: model.meeting)
            .frame(width: Self.sidebarWidth)
    }

    /// The page, sliding in from the side it lies on: deeper pages from the right, back from the left.
    private func pages(narrow: Bool) -> some View {
        VStack(spacing: 0) {
            if narrow { narrowBar }
            ZStack {
                page
                    .id(route.page)
                    .transition(transition)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .clipped()
            .animation(theme.motion.animation(reduced: reduceMotion), value: route.page)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var transition: AnyTransition {
        if reduceMotion { return .opacity }
        let x: CGFloat = route.forward ? 28 : -28
        return .asymmetric(insertion: .offset(x: x).combined(with: .opacity),
                           removal: .offset(x: -x / 2).combined(with: .opacity))
    }

    @ViewBuilder private var page: some View {
        switch route.page {
        case .today:
            VStack(spacing: 0) {
                TodayView(transcript: transcript, model: model, route: route, talkKey: settings.talkKey,
                          actions: actions, changeDraft: { settings.prefill = "Change \($0.name): " })
                InputBar(speakReplies: $speakReplies, prefill: $settings.prefill, placeholder: "Type to Milo",
                         focusTick: settings.typeHere) { text in
                    actions.send(text, speakReplies, "")
                    route.go(.live)
                }
            }
        case .usage:
            UsageView(usage: usage, model: model)
        case .live:
            conversation(transcript.current)
        case let .conversation(id):
            conversation(id)
        case let .task(id):
            if let (entry, conversation) = transcript.task(id) {
                TaskPage(entry: entry, conversation: conversation ?? transcript.conversation(ofTask: id),
                         helper: model.helpers.first { $0.id == id }, undo: model.undoPoint(id), undoTask: model.undo,
                         openConversation: { open($0) }, stop: model.stopHelper, reveal: actions.reveal)
            } else {
                TaskMissing(loading: transcript.conversation(ofTask: id) != nil, back: route.goBack)
            }
        }
    }

    @ViewBuilder private func conversation(_ id: String) -> some View {
        if let info = transcript.info(id), info.kind == .meeting, case let meeting = MeetingPageID.meeting(of: info),
           !meeting.isEmpty {
            MeetingPage(meeting: model.meeting, transcript: transcript, id: meeting, conversation: id, actions: actions)
        } else {
            ConversationPage(transcript: transcript, model: model, settings: settings, route: route, id: id,
                             actions: actions)
        }
    }

    /// In a narrow window: the sidebar button, the way back, and where you are.
    private var narrowBar: some View {
        HStack(spacing: 6) {
            BarButton(icon: "sidebar.left", help: "Show the conversations (⌘0)") { route.sidebarShown.toggle() }
            if route.page != .today && route.page != .live && route.page != .usage {
                BarButton(icon: "chevron.left", help: "Back (⌘[)", action: route.goBack)
            }
            Spacer()
            if route.page != .today {
                BarButton(icon: "sun.max", help: "Today (⌘1)") { route.go(.today) }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }

    // ---- what the keys do

    /// Buttons nobody sees, for the window's shortcuts.
    private var shortcuts: some View {
        ZStack {
            Button("Today") { route.go(.today) }.keyboardShortcut("1", modifiers: .command)
            Button("Usage") { route.go(.usage) }.keyboardShortcut("2", modifiers: .command)
            Button("New conversation") { actions.newConversation(); route.go(.live) }
                .keyboardShortcut("n", modifiers: .command)
            Button("Search") { route.sidebarShown = true; searching = true }.keyboardShortcut("f", modifiers: .command)
            Button("Back") { route.goBack() }.keyboardShortcut("[", modifiers: .command)
            Button("Previous conversation") { step(-1) }.keyboardShortcut(.upArrow, modifiers: [.command, .option])
            Button("Next conversation") { step(1) }.keyboardShortcut(.downArrow, modifiers: [.command, .option])
            Button("Type") { settings.typeHere += 1 }.keyboardShortcut("l", modifiers: .command)
            Button("Sidebar") { route.sidebarShown.toggle() }.keyboardShortcut("0", modifiers: .command)
            Button("Escape") { escape() }.keyboardShortcut(.escape, modifiers: [])
        }
        .opacity(0)
        .frame(width: 0, height: 0)
        .accessibilityHidden(true)
    }

    private func escape() {
        if !route.search.isEmpty { route.search = ""; searching = false }
        else if route.sidebarShown { route.sidebarShown = false }
        else if case .task = route.page { route.goBack() }
    }

    /// The conversation above or below the one shown, in the sidebar's order.
    private func step(_ by: Int) {
        let list = DayGroups.group(transcript.conversations, now: ConversationsSidebar.now()).flatMap(\.items)
        guard !list.isEmpty else { return }
        let shown = route.conversation(current: transcript.current)
        let i = shown.flatMap { id in list.firstIndex { $0.id == id } }
        let next = i.map { min(max($0 + by, 0), list.count - 1) } ?? (by > 0 ? 0 : list.count - 1)
        open(list[next].id)
    }

    private func open(_ id: String) {
        if id == transcript.current { route.go(.live) } else {
            actions.open(id)
            route.go(.conversation(id))
        }
    }

    /// Ask a moment after the typing stops.
    private func searchChanged() {
        pendingSearch?.cancel()
        let query = route.search.trimmingCharacters(in: .whitespaces)
        guard !query.isEmpty else { transcript.clearSearch(); return }
        pendingSearch = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(250))
            guard !Task.isCancelled else { return }
            actions.search(query)
        }
    }

    private var waiting: Int {
        (model.question == nil ? 0 : 1) + model.drafts.count
    }

}

/// A small icon button in the narrow window's bar.
private struct BarButton: View {
    @Environment(\.miloTheme) private var theme
    let icon: String
    let help: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(theme.ink.opacity(0.6))
                .frame(width: 26, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(help)
        .accessibilityLabel(help)
    }
}

/// The transcript without scrolling, so it can also be rendered offscreen.
struct TranscriptList: View {
    let entries: [TranscriptEntry]
    let state: MiloState
    var helpers: [HelperInfo] = []
    /// Tasks show as cards that open their page; without it, as blocks with their steps.
    var openTask: ((String) -> Void)?
    var undoPoints: [UndoPoint] = []
    var undoTask: (String) -> Void = { _ in }

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(Array(entries.enumerated()), id: \.element.id) { i, entry in
                let previous = i > 0 ? entries[i - 1] : nil
                if let day = DayHeading.text(for: entry.date, after: previous?.date) {
                    DayHeading(text: day).padding(.top, i == 0 ? 0 : 14).padding(.bottom, 10)
                }
                EntryRow(entry: entry, showTime: Self.showsTime(entry, after: previous), helper: helpers.first { $0.id == entry.id },
                         openTask: openTask, undo: undoPoints.first { $0.id == entry.id }, undoTask: undoTask)
                    .padding(.top, Self.gap(entry, after: previous))
                    .id(entry.id)
            }
            if let pending = PendingRow.text(for: state, last: entries.last) {
                PendingRow(text: pending, state: state)
                    .padding(.top, entries.isEmpty ? 0 : 14)
            }
        }
    }

    /// A new time only when the minute changes.
    static func showsTime(_ entry: TranscriptEntry, after previous: TranscriptEntry?) -> Bool {
        guard let previous else { return true }
        let calendar = Calendar.current
        return !calendar.isDate(entry.date, equalTo: previous.date, toGranularity: .minute)
    }

    /// More air before the user speaks than between Milo's answer and his work on it.
    static func gap(_ entry: TranscriptEntry, after previous: TranscriptEntry?) -> CGFloat {
        guard previous != nil else { return 0 }
        return entry.kind == .user ? 18 : 8
    }
}

struct EntryRow: View {
    let entry: TranscriptEntry
    let showTime: Bool
    var helper: HelperInfo?
    var openTask: ((String) -> Void)?
    var undo: UndoPoint?
    var undoTask: (String) -> Void = { _ in }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(showTime ? entry.date.formatted(date: .omitted, time: .shortened) : "")
                .font(.system(size: 10.5).monospacedDigit())
                .foregroundStyle(.tertiary)
                .frame(width: Layout.gutter, alignment: .trailing)
            switch entry.kind {
            case .user: UserLine(entry: entry)
            case .milo:
                if entry.written {
                    WrittenBlock(text: entry.text)
                } else {
                    MiloLine(text: entry.text, emotion: entry.emotion, streaming: !entry.done)
                }
            case .task:
                if let openTask {
                    TaskCard(entry: entry, helper: helper, undo: entry.status == .running ? nil : undo,
                             undoTask: undoTask, open: { openTask(entry.id) })
                } else {
                    TaskBlock(entry: entry)
                }
            }
        }
    }
}

enum Layout {
    static let gutter: CGFloat = 46
}

/// What the user said, quieter than Milo, with how it was said.
struct UserLine: View {
    let entry: TranscriptEntry

    static let icon: [TranscriptEntry.Via: String] = [.voice: "mic.fill", .typed: "keyboard", .message: "iphone"]
    static let help: [TranscriptEntry.Via: String] = [.voice: "You said this", .typed: "You typed this",
                                                      .message: "You sent this from your phone"]

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Image(systemName: Self.icon[entry.via] ?? "mic.fill")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 12)
                .help(Self.help[entry.via] ?? "You said this")
            Text(entry.text)
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// Milo's words: the rounded face of the app, with a small dot in the colour of his mood.
struct MiloLine: View {
    @Environment(\.miloTheme) private var theme
    let text: String
    let emotion: Emotion
    var streaming = false

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Circle()
                .fill(WindowColors.mood(emotion, theme))
                .frame(width: 7, height: 7)
                .frame(width: 12)
                .help("Milo felt \(emotion.rawValue)")
                .accessibilityLabel("Milo, \(emotion.rawValue)")
            (Text(text) + Text(streaming ? " ▍" : "").foregroundColor(theme.primary))
                .font(.system(size: 14, design: .rounded))
                .lineSpacing(2.5)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// Text Milo wrote for the user (ADR 0033), as he wrote it, with a button that copies it: it may have gone into
/// their field, or be waiting here because it couldn't.
struct WrittenBlock: View {
    @Environment(\.miloTheme) private var theme
    let text: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(text)
                .font(.system(size: 13.5))
                .foregroundStyle(theme.ink)
                .lineSpacing(2.5)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button(action: copy) {
                Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 11.5, weight: .semibold, design: .rounded))
            }
            .buttonStyle(.plain)
            .foregroundStyle(theme.primary)
            .help("Copies the text, to paste it yourself")
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(theme.rule))
        .padding(.leading, 19)  // under Milo's words, past his dot
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Text Milo wrote")
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        copied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { copied = false }
    }
}

struct DayHeading: View {
    @Environment(\.miloTheme) private var theme
    let text: String

    var body: some View {
        HStack(spacing: 10) {
            Text(text)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Rectangle().fill(theme.rule).frame(height: 1)
        }
        .padding(.leading, Layout.gutter + 10)
    }

    /// "Today", "Yesterday" or a date, when `date` falls on another day than `previous`.
    static func text(for date: Date, after previous: Date?, calendar: Calendar = .current) -> String? {
        if let previous, calendar.isDate(date, inSameDayAs: previous) { return nil }
        if calendar.isDateInToday(date) { return "Today" }
        if calendar.isDateInYesterday(date) { return "Yesterday" }
        return date.formatted(.dateTime.weekday(.wide).day().month(.wide))
    }
}

/// "Listening…" or "Thinking…" at the end while nothing has arrived yet.
struct PendingRow: View {
    @Environment(\.miloTheme) private var theme
    let text: String
    let state: MiloState

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            Color.clear.frame(width: Layout.gutter, height: 1)
            if state == .listening {
                LevelBars(level: 0.35, color: theme.primary).frame(width: 12).scaleEffect(0.6)
            } else {
                ThinkingDots(color: theme.accent).scaleEffect(0.55).frame(width: 12)
            }
            Text(text)
                .font(.system(size: 12.5, design: .rounded))
                .foregroundStyle(.secondary)
        }
    }

    static func text(for state: MiloState, last: TranscriptEntry?) -> String? {
        switch state {
        case .listening: "Listening…"
        case .transcribing: "Writing down what you said…"
        case .thinking where !(last?.kind == .milo && last?.done == false): "Thinking…"
        default: nil
        }
    }
}

/// The first thing a new user sees: talk first, typing second.
struct EmptyConversation: View {
    @Environment(\.miloTheme) private var theme
    let talkKey: String

    var body: some View {
        VStack(spacing: 12) {
            Spacer()
            CharacterFigure(emotion: .happy, size: 72)
                .frame(width: 72, height: 72)
                .background(Circle().fill(RadialGradient(colors: [theme.glow.opacity(0.45), theme.glow.opacity(0)], center: .center, startRadius: 4, endRadius: 50)).frame(width: 110, height: 110))
            Text("Hold \(talkKey) and talk, or type here.")
                .font(.system(size: 15, weight: .medium, design: .rounded))
                .multilineTextAlignment(.center)
            Text("What you say, what Milo answers and what he does for you shows up here.")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 260)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(24)
    }
}

/// Milo's waiting question, pinned above the text field until it is answered.
struct QuestionBar: View {
    @Environment(\.miloTheme) private var theme
    let question: PendingQuestion
    let talkKey: String
    let answer: (Answer) -> Void
    var choose: (ConfirmChoice) -> Void = { _ in }

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(question.text)
                    .font(.system(size: 13.5, weight: .medium, design: .rounded))
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
                if question.money {
                    Label("This involves money. \(QuestionView.moneyNote)", systemImage: "creditcard.fill")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(theme.accent)
                        .labelStyle(TightLabel())
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    Text("Or hold \(talkKey) and say yes or no.")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            AnswerButtons(always: question.always, choices: question.choices, answer: answer, choose: choose)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(theme.ink.opacity(0.05))
        .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(question.money ? "Milo asks about money: \(question.text)" : "Milo asks: \(question.text)")
    }
}

struct InputBar: View {
    @Environment(\.miloTheme) private var theme
    @Binding var speakReplies: Bool
    @Binding var prefill: String?
    var placeholder = "Type to Milo"
    /// Changes when ⌘L asks for the cursor.
    var focusTick = 0
    let submit: (String) -> Void
    @State private var draft = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            TextField(placeholder, text: $draft)
                .textFieldStyle(.plain)
                .focusEffectDisabled()
                .font(.system(size: 13.5))
                .focused($focused)
                .onSubmit(send)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                // Keep the radius under half the field's height (~32 pt): from about there on, the border
                // renders with a short vertical bar at each end.
                .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(theme.card))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(focused ? theme.primary.opacity(0.55) : theme.rule, lineWidth: 1))
            Button {
                speakReplies.toggle()
            } label: {
                Image(systemName: speakReplies ? "speaker.wave.2.fill" : "speaker.slash")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(speakReplies ? theme.primary : Color.secondary)
                    .frame(width: 30, height: 34)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(speakReplies ? "Milo reads his answers aloud. Click to keep them silent."
                               : "Milo answers typed messages silently. Click to hear them.")
            .accessibilityLabel("Speak replies")
            .accessibilityValue(speakReplies ? "on" : "off")
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 14)
        .background(theme.tint)
        .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
        .onAppear { focused = true }
        .onChange(of: focusTick) { focused = true }
        .onChange(of: prefill) {
            guard let text = prefill else { return }
            draft = text
            focused = true
            prefill = nil
        }
    }

    private func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        submit(text)
        draft = ""
    }
}

/// Colours for what a task is doing, the same under every skin, and the dot by Milo's lines.
/// Everything else in the window comes from the skin's `Theme`.
enum WindowColors {
    static let running = dynamic(light: NSColor(Palette.think).blended(withFraction: 0.25, of: .black)!,
                                 dark: NSColor(Palette.think))
    static let done = dynamic(light: NSColor(Palette.dictate).blended(withFraction: 0.35, of: .black)!,
                              dark: NSColor(Palette.dictate))
    static let failed = dynamic(light: NSColor(Palette.talk).blended(withFraction: 0.18, of: .black)!,
                                dark: NSColor(Palette.talk))

    static func mood(_ emotion: Emotion, _ theme: Theme) -> Color {
        switch emotion {
        case .neutral: theme.primary
        case .happy: Palette.think
        case .excited: theme.accent
        case .thinking: Palette.speak
        case .concerned, .confused: Palette.talk
        case .sad: theme.primary.opacity(0.6)
        case .sleepy: theme.glow
        }
    }

    static func status(_ status: ActivityStep.Status) -> Color {
        switch status {
        case .running: running
        case .done: done
        case .failed: failed
        }
    }

    private static func dynamic(light: NSColor, dark: NSColor) -> Color {
        Color(nsColor: dynamicNS(light: light, dark: dark))
    }

    private static func dynamicNS(light: NSColor, dark: NSColor) -> NSColor {
        ThemeColors.dynamic((light, dark))
    }
}
