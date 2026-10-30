import AppKit
import SwiftUI

/// What the Milo window needs besides the transcript: the talk key's name for the empty state.
public final class ConversationSettings: ObservableObject {
    @Published public var talkKey: String
    /// The task entry to scroll to, set when the user clicks a helper.
    @Published public var focus: String?
    /// Text to put in the field, ready to finish and send: "Change it" on a recipe draft.
    @Published public var prefill: String?

    public init(talkKey: String) {
        self.talkKey = talkKey
    }
}

/// The Milo window: the conversation as text, what Milo is doing, and a field to type to him.
public struct ConversationView: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var transcript: TranscriptModel
    @ObservedObject var model: MiloModel
    @ObservedObject var settings: ConversationSettings
    let send: (_ text: String, _ speak: Bool) -> Void

    @AppStorage("speakTypedReplies") private var speakReplies = false
    @AppStorage("showRoutines") private var showRoutines = false

    public init(transcript: TranscriptModel, model: MiloModel, settings: ConversationSettings,
                send: @escaping (_ text: String, _ speak: Bool) -> Void) {
        self.transcript = transcript
        self.model = model
        self.settings = settings
        self.send = send
    }

    public var body: some View {
        VStack(spacing: 0) {
            if !model.routines.isEmpty {
                RoutinesPanel(routines: model.routines, open: $showRoutines, act: model.routine)
            }
            if !model.helpers.isEmpty {
                HelpersPanel(helpers: model.helpers, entries: transcript.entries, character: model.character,
                             open: { settings.focus = $0 }, stop: model.stopHelper)
            }
            if transcript.entries.isEmpty && model.state == .idle {
                EmptyConversation(talkKey: settings.talkKey)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        TranscriptList(entries: transcript.entries, state: model.state)
                            .padding(.horizontal, 18)
                            .padding(.top, 14)
                            .padding(.bottom, 10)
                        Color.clear.frame(height: 1).id(Self.bottom)
                    }
                    .onAppear { proxy.scrollTo(settings.focus ?? Self.bottom, anchor: settings.focus == nil ? .bottom : .top) }
                    .onChange(of: scrollKey) { if settings.focus == nil { proxy.scrollTo(Self.bottom, anchor: .bottom) } }
                    .onChange(of: settings.focus) {
                        guard let focus = settings.focus else { return }
                        withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo(focus, anchor: .top) }
                        // Following new lines again after a moment, so the next turn still scrolls into view.
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                            if settings.focus == focus { settings.focus = nil }
                        }
                    }
                }
            }
            if let draft = model.drafts.last {
                DraftCard(draft: draft, talkKey: settings.talkKey,
                          save: { model.answerDraft(draft.id, save: true) },
                          change: { settings.prefill = "Change \(draft.name): " },
                          drop: { model.answerDraft(draft.id, save: false) })
            }
            if let question = model.question {
                QuestionBar(question: question, talkKey: settings.talkKey, answer: model.answer)
            }
            InputBar(speakReplies: $speakReplies, prefill: $settings.prefill) { send($0, speakReplies) }
        }
        .background(theme.tint)
        .animation(theme.motion.gentle, value: theme)
    }

    private static let bottom = "bottom"

    /// Changes whenever something new appears at the end, so the list follows it.
    private var scrollKey: String {
        let last = transcript.entries.last
        return "\(transcript.entries.count)-\(last?.text.count ?? 0)-\(last?.steps.count ?? 0)-\(model.state)"
    }
}

/// The transcript without scrolling, so it can also be rendered offscreen.
struct TranscriptList: View {
    let entries: [TranscriptEntry]
    let state: MiloState

    var body: some View {
        LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(Array(entries.enumerated()), id: \.element.id) { i, entry in
                let previous = i > 0 ? entries[i - 1] : nil
                if let day = DayHeading.text(for: entry.date, after: previous?.date) {
                    DayHeading(text: day).padding(.top, i == 0 ? 0 : 14).padding(.bottom, 10)
                }
                EntryRow(entry: entry, showTime: Self.showsTime(entry, after: previous))
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

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(showTime ? entry.date.formatted(date: .omitted, time: .shortened) : "")
                .font(.system(size: 10.5).monospacedDigit())
                .foregroundStyle(.tertiary)
                .frame(width: Layout.gutter, alignment: .trailing)
            switch entry.kind {
            case .user: UserLine(entry: entry)
            case .milo: MiloLine(text: entry.text, emotion: entry.emotion, streaming: !entry.done)
            case .task: TaskBlock(entry: entry)
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

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Image(systemName: entry.via == .typed ? "keyboard" : "mic.fill")
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 12)
                .help(entry.via == .typed ? "You typed this" : "You said this")
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
            CharacterFigure(for: theme.style, emotion: .happy, size: 72)
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
    let answer: (Bool) -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(question.text)
                    .font(.system(size: 13.5, weight: .medium, design: .rounded))
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
                Text("Or hold \(talkKey) and say yes or no.")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            AnswerButtons(answer: answer)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(theme.ink.opacity(0.05))
        .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Milo asks: \(question.text)")
    }
}

struct InputBar: View {
    @Environment(\.miloTheme) private var theme
    @Binding var speakReplies: Bool
    @Binding var prefill: String?
    let submit: (String) -> Void
    @State private var draft = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            TextField("Type to Milo", text: $draft)
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
