import SwiftUI

/// Where a meeting's page finds its meeting.
enum MeetingPageID {
    /// The meeting folder's name from a meeting conversation's `source`, "meeting:<id>"; "" for others.
    static func meeting(of conversation: ConversationInfo) -> String {
        conversation.source.hasPrefix("meeting:") ? String(conversation.source.dropFirst("meeting:".count)) : ""
    }

    /// A meeting conversation's preview without "Notes from “Weekly sync”: " in front.
    static func summary(of preview: String) -> String {
        guard preview.hasPrefix("Notes from “"), let colon = preview.range(of: "”: ") else { return preview }
        return String(preview[colon.upperBound...])
    }

    /// The first sentence of `text`, for a one-line row.
    static func firstSentence(_ text: String) -> String {
        guard let end = text.firstIndex(where: { ".!?".contains($0) }) else { return text }
        return String(text[...end])
    }
}

/// A meeting in the Milo window. While it goes on: who speaks, the transcript as it comes in, Pause and Stop, a note
/// to paste in the call's chat, and a field to ask about it. Afterwards: the notes, the to-dos with "Add to
/// Reminders", and the transcript. See docs/design/meetings.md.
struct MeetingPage: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var meeting: MeetingModel
    @ObservedObject var transcript: TranscriptModel
    let id: String
    let conversation: String
    let actions: WindowActions
    @State private var tab = MeetingPage.startTab
    /// The tab a page opens on; renders set it.
    static var startTab = Tab.notes
    @State private var speak = false
    @State private var prefill: String?
    /// The notes didn't come: the page shows the meeting's conversation as it is.
    @State private var missing = false

    enum Tab: String, CaseIterable { case notes = "Notes", todos = "To-dos", transcript = "Transcript" }

    private var current: Bool { meeting.isCurrent(id) }
    private var info: ConversationInfo? { transcript.info(conversation) }

    var body: some View {
        VStack(spacing: 0) {
            if current {
                live
            } else if let notes = meeting.notes[id] {
                done(notes)
            } else if missing {
                VStack(spacing: 0) {
                    ScrollView {
                        TranscriptList(entries: transcript.entries(of: conversation), state: .idle)
                            .padding(.horizontal, 18)
                            .padding(.vertical, 14)
                    }
                    InputBar(speakReplies: $speak, prefill: $prefill, placeholder: "Ask about this meeting") {
                        actions.send($0, speak, conversation)
                    }
                }
            } else {
                opening
            }
        }
        .onAppear { meeting.request(id) }
        .task(id: id) {
            try? await Task.sleep(for: .seconds(3))
            missing = meeting.notes[id] == nil && !meeting.isCurrent(id)
        }
    }

    // MARK: Live

    private var live: some View {
        let status = meeting.status
        return VStack(spacing: 0) {
            LiveMeetingHeader(meeting: meeting)
            if status.live { ConsentRow(meeting: meeting) }
            MeetingTranscript(lines: meeting.lines[id] ?? [], phase: status.phase, step: status.step, live: true)
            AskAboutMeeting(entries: questions, suggestions: ["What did I miss?", "Sum up the last ten minutes"],
                            prefill: $prefill)
            InputBar(speakReplies: $speak, prefill: $prefill, placeholder: "Ask about this meeting") {
                actions.send($0, speak, conversation)
            }
        }
    }

    /// The user's questions in the meeting's conversation and Milo's answers.
    private var questions: [TranscriptEntry] {
        let all = transcript.entries(of: conversation)
        guard let first = all.firstIndex(where: { $0.kind == .user }) else { return [] }
        return all[first...].filter { $0.kind == .user || $0.kind == .milo }
    }

    // MARK: Done

    private func done(_ notes: MeetingNotes) -> some View {
        VStack(spacing: 0) {
            NotesHeader(notes: notes, meeting: meeting, reveal: actions.reveal)
            TabStrip(tab: $tab, todos: notes.todos.count, lines: (meeting.lines[id] ?? []).count)
            ZStack {
                switch tab {
                case .notes:
                    ScrollView {
                        VStack(alignment: .leading, spacing: 18) {
                            MarkdownView(blocks: NotesPage.blocks(notes.markdown))
                            if notes.mail && !notes.followup.isEmpty {
                                Button(notes.mailDrafted ? "The draft is in Mail" : "Put the mail in Mail as a draft") {
                                    meeting.draftMail(id)
                                }
                                .buttonStyle(PageButtonStyle(prominent: !notes.mailDrafted))
                                .disabled(notes.mailDrafted)
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.vertical, 18)
                        .frame(maxWidth: 680, alignment: .leading)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                case .todos:
                    TodoList(notes: notes, add: { meeting.addTodo(id, $0) })
                case .transcript:
                    MeetingTranscript(lines: meeting.lines[id] ?? [], phase: .done, step: "", live: false)
                }
            }
            .frame(maxHeight: .infinity)
            .environment(\.openURL, OpenURLAction { url in
                // "[The whole transcript](transcript.md)" at the end of the notes: the tab, not the file.
                if url.scheme == nil, url.path.hasSuffix("transcript.md") {
                    tab = .transcript
                    return .handled
                }
                return .systemAction
            })
            AskAboutMeeting(entries: questions, suggestions: ["What do I need to do?", "Write a short recap"],
                            prefill: $prefill)
            InputBar(speakReplies: $speak, prefill: $prefill, placeholder: "Ask about this meeting") {
                actions.send($0, speak, conversation)
            }
        }
    }

    private var opening: some View {
        VStack(spacing: 10) {
            ThinkingDots(color: theme.primary)
            Text("Opening the notes…")
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(theme.ink.opacity(0.6))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// What the Notes tab shows of notes.md: all of it but the title and date (the header has them) and the to-dos
/// (their own tab).
enum NotesPage {
    static func blocks(_ markdown: String) -> [MarkdownBlock] {
        var blocks = MarkdownBlock.parse(markdown)
        if case .heading(1, _) = blocks.first {
            blocks.removeFirst()
            if case .paragraph = blocks.first { blocks.removeFirst() }
        }
        var kept: [MarkdownBlock] = []
        var skipping = false
        for block in blocks {
            if case let .heading(level, text) = block, level <= 2 {
                skipping = text.lowercased().hasPrefix("to-do") || text.lowercased().hasPrefix("todo")
            }
            if !skipping { kept.append(block) }
        }
        return kept
    }
}

/// The top of a meeting going on: the light, the title, the time, who was heard, Pause and Stop.
struct LiveMeetingHeader: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var meeting: MeetingModel

    var body: some View {
        let status = meeting.status
        HStack(alignment: .center, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 9, style: .continuous).fill(MeetingColors.live.opacity(0.12))
                if status.phase == .writing {
                    Image(systemName: "pencil.line").font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(theme.primary)
                } else {
                    LiveLight(paused: status.phase == .paused)
                }
            }
            .frame(width: 34, height: 34)
            VStack(alignment: .leading, spacing: 3) {
                Text(status.title.isEmpty ? "Meeting" : status.title)
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                    .foregroundStyle(theme.ink)
                    .lineLimit(1)
                TimelineView(.periodic(from: .now, by: 1)) { _ in
                    Text(Self.subline(status, elapsed: meeting.elapsed()))
                        .font(.system(size: 12, weight: .medium).monospacedDigit())
                        .foregroundStyle(theme.ink.opacity(0.6))
                        .lineLimit(1)
                }
                if !status.speakers.isEmpty {
                    SpeakerChips(names: status.speakers)
                }
            }
            Spacer(minLength: 8)
            if status.live {
                Button(status.phase == .paused ? "Go on" : "Pause") { meeting.pause(status.phase != .paused) }
                    .buttonStyle(PageButtonStyle(prominent: false))
                    .help(status.phase == .paused ? "Go on taking notes" : "Leave the next part out of the notes")
                StopButton(compact: false) { meeting.stop() }
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }

    static func subline(_ status: MeetingStatus, elapsed: TimeInterval) -> String {
        let app = status.app.isEmpty ? "" : " · \(status.app)"
        switch status.phase {
        case .paused: return "Paused at \(MeetingModel.clock(elapsed)) · nothing goes into the notes now"
        case .writing: return status.step.isEmpty ? "Writing your notes…" : "Writing your notes · \(status.step)"
        default: return "Taking notes · \(MeetingModel.clock(elapsed))\(app)"
        }
    }
}

/// Who was heard, each in the colour their lines wear.
struct SpeakerChips: View {
    @Environment(\.miloTheme) private var theme
    let names: [String]

    var body: some View {
        HStack(spacing: 6) {
            ForEach(Array(names.prefix(6).enumerated()), id: \.offset) { _, name in
                HStack(spacing: 4) {
                    Circle().fill(SpeakerColors.color(name, in: names, theme)).frame(width: 6, height: 6)
                    Text(name).font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(theme.ink.opacity(0.7))
                }
            }
            if names.count > 6 {
                Text("+\(names.count - 6)").font(.system(size: 11)).foregroundStyle(theme.ink.opacity(0.5))
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Heard so far: \(names.joined(separator: ", "))")
    }
}

/// A speaker's colour: the user in Milo's lavender, everyone else in turn from a warm palette.
enum SpeakerColors {
    static func color(_ name: String, in names: [String], _ theme: Theme) -> Color {
        if name == "You" { return theme.primary }
        if name == "Others" { return theme.ink.opacity(0.45) }
        let others = names.filter { $0 != "You" && $0 != "Others" }
        return MeetingColors.speaker(others.firstIndex(of: name) ?? abs(name.hashValue), theme)
    }
}

/// "Tell the others?" with the line to paste into the call's chat.
struct ConsentRow: View {
    @Environment(\.miloTheme) private var theme
    @ObservedObject var meeting: MeetingModel

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "text.bubble")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(theme.accent)
            VStack(alignment: .leading, spacing: 1) {
                Text("Let the others know")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.85))
                Text("“\(meeting.status.consent.isEmpty ? MeetingModel.consent : meeting.status.consent)”")
                    .font(.system(size: 11.5))
                    .foregroundStyle(theme.ink.opacity(0.6))
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Button(meeting.copied ? "Copied" : "Copy for the chat") { meeting.copyConsent() }
                .buttonStyle(PageButtonStyle(prominent: false))
                .accessibilityHint("Puts the line on the clipboard, to paste into the call's chat")
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 9)
        .background(theme.accent.opacity(0.07))
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }
}

/// The meeting's lines: a name when the speaker changes, the time into the meeting, the words. Live, it follows new
/// lines until the user scrolls up, offers "Back to now", and ends with a row that says the last minute comes later.
struct MeetingTranscript: View {
    @Environment(\.miloTheme) private var theme
    let lines: [MeetingLine]
    let phase: MeetingStatus.Phase
    let step: String
    let live: Bool
    @State private var follow = TranscriptFollow()
    @State private var viewport: CGFloat = 0

    private var names: [String] {
        var seen: [String] = []
        for line in lines where !seen.contains(line.who) { seen.append(line.who) }
        return seen
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if lines.isEmpty && !live {
                        Text("No transcript for this meeting.")
                            .font(.system(size: 13))
                            .foregroundStyle(theme.ink.opacity(0.5))
                            .padding(.vertical, 20)
                    }
                    ForEach(Array(lines.enumerated()), id: \.element.id) { index, line in
                        LineRow(line: line, named: index == 0 || lines[index - 1].who != line.who,
                                color: SpeakerColors.color(line.who, in: names, theme))
                    }
                    if live { LagRow(phase: phase, step: step, empty: lines.isEmpty) }
                    Color.clear.frame(height: 1).id(Self.end)
                        .background(GeometryReader { g in
                            Color.clear.preference(key: EndOffset.self, value: g.frame(in: .named(Self.space)).maxY)
                        })
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 14)
            }
            .defaultScrollAnchor(live ? .bottom : .top)
            .coordinateSpace(name: Self.space)
            .background(GeometryReader { g in Color.clear.onAppear { viewport = g.size.height }
                .onChange(of: g.size.height) { viewport = g.size.height } })
            .onPreferenceChange(EndOffset.self) { maxY in
                follow.scrolled(distanceToEnd: maxY - viewport)
            }
            .onAppear { proxy.scrollTo(Self.end, anchor: .bottom) }
            .onChange(of: lines.count) { old, new in
                if follow.arrived(new - old) {
                    withAnimation(theme.motion.gentle) { proxy.scrollTo(Self.end, anchor: .bottom) }
                }
            }
            .overlay(alignment: .bottom) {
                if live && !follow.following {
                    Button {
                        follow.jump()
                        withAnimation(theme.motion.gentle) { proxy.scrollTo(Self.end, anchor: .bottom) }
                    } label: {
                        Label(follow.unseen > 0 ? "Back to now · \(follow.unseen) new" : "Back to now",
                              systemImage: "arrow.down")
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .foregroundStyle(theme.onPrimary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Capsule().fill(theme.primary))
                            .shadow(color: theme.primary.opacity(0.25), radius: 6, y: 2)
                    }
                    .buttonStyle(.plain)
                    .padding(.bottom, 10)
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
                }
            }
            .animation(theme.motion.spring, value: follow.following)
        }
    }

    private static let end = "end"
    private static let space = "meeting-transcript"
}

private struct EndOffset: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// One line of the transcript.
struct LineRow: View {
    @Environment(\.miloTheme) private var theme
    let line: MeetingLine
    /// The first of a run by one speaker: the name shows.
    let named: Bool
    let color: Color

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(MeetingModel.clock(line.at))
                .font(.system(size: 11).monospacedDigit())
                .foregroundStyle(theme.ink.opacity(0.4))
                .frame(width: 44, alignment: .trailing)
            VStack(alignment: .leading, spacing: 2) {
                if named {
                    Text(line.who)
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(color)
                }
                Text(line.text)
                    .font(.system(size: 13.5))
                    .lineSpacing(2)
                    .foregroundStyle(theme.ink.opacity(0.9))
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.leading, 10)
            .overlay(alignment: .leading) { Capsule().fill(color.opacity(0.5)).frame(width: 2.5) }
        }
        .padding(.top, named ? 12 : 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(line.who) at \(MeetingModel.clock(line.at)): \(line.text)")
    }
}

/// The end of a live transcript: the words come about a minute late, and this says so.
struct LagRow: View {
    @Environment(\.miloTheme) private var theme
    let phase: MeetingStatus.Phase
    let step: String
    let empty: Bool

    var body: some View {
        HStack(spacing: 10) {
            ThinkingDots(color: theme.primary.opacity(phase == .paused ? 0.35 : 1))
                .frame(width: 44, alignment: .trailing)
            Text(text)
                .font(.system(size: 12.5, weight: .medium, design: .rounded))
                .foregroundStyle(theme.ink.opacity(0.55))
        }
        .padding(.top, 16)
        .accessibilityElement(children: .combine)
    }

    private var text: String {
        switch phase {
        case .paused: "Paused. Nothing said now goes into the notes."
        case .writing: step.isEmpty ? "Writing your notes…" : "\(step)…"
        default: empty ? "Listening… the first words show up in about a minute."
                       : "Listening… the last minute shows up shortly."
        }
    }
}

/// Questions about the meeting so far, Milo's answers, and a few ready ones to ask.
struct AskAboutMeeting: View {
    @Environment(\.miloTheme) private var theme
    let entries: [TranscriptEntry]
    let suggestions: [String]
    @Binding var prefill: String?

    private var answers: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(entries.suffix(6), id: \.id) { entry in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(entry.kind == .user ? "You" : "Milo")
                        .font(.system(size: 11.5, weight: .semibold, design: .rounded))
                        .foregroundStyle(entry.kind == .user ? theme.ink.opacity(0.55) : theme.primary)
                        .frame(width: 32, alignment: .leading)
                    Text(entry.text)
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink.opacity(0.9))
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !entries.isEmpty {
                // As tall as the answers, at most 140 points; past that they scroll, the newest in view.
                Capped(height: 140) {
                    ViewThatFits(in: .vertical) {
                        answers
                        ScrollView { answers }
                            .defaultScrollAnchor(.bottom)
                    }
                }
            }
            HStack(spacing: 6) {
                ForEach(suggestions, id: \.self) { question in
                    Button(question) { prefill = question }
                        .buttonStyle(QuietChoiceStyle())
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
    }
}

/// The top of finished notes: the title, when and how long, who was there, Copy and Show in Finder.
struct NotesHeader: View {
    @Environment(\.miloTheme) private var theme
    let notes: MeetingNotes
    @ObservedObject var meeting: MeetingModel
    let reveal: (String) -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: "person.2.fill")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(theme.accent)
                .frame(width: 34, height: 34)
                .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(theme.accent.opacity(0.14)))
            VStack(alignment: .leading, spacing: 3) {
                Text(notes.title.isEmpty ? "Meeting" : notes.title)
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                    .foregroundStyle(theme.ink)
                    .lineLimit(1)
                Text(Self.subline(notes))
                    .font(.system(size: 12))
                    .foregroundStyle(theme.ink.opacity(0.58))
                    .lineLimit(1)
            }
            .frame(minWidth: 190, alignment: .leading)
            Spacer(minLength: 8)
            // Words where there is room, only their icons where there isn't: the title keeps its place.
            ViewThatFits(in: .horizontal) {
                buttons(.titleAndIcon)
                buttons(.iconOnly)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
    }

    private func buttons(_ style: some LabelStyle) -> some View {
        HStack(spacing: 8) {
            Button {
                meeting.copyNotes(notes.id)
            } label: {
                Label(meeting.copiedNotes == notes.id ? "Copied" : "Copy notes",
                      systemImage: meeting.copiedNotes == notes.id ? "checkmark" : "doc.on.doc")
                    .labelStyle(style)
            }
            .help("Copy the notes, to paste them anywhere")
            if !notes.folder.isEmpty {
                Button { reveal(notes.folder + "/notes.md") } label: {
                    Label("Show in Finder", systemImage: "folder").labelStyle(style)
                }
                .help("Show notes.md in the Finder")
            }
        }
        .buttonStyle(PageButtonStyle(prominent: false))
    }

    /// "Thu 30 Oct, 14:00 · 30 min · Zoom · with Anna and Ben"
    static func subline(_ notes: MeetingNotes) -> String {
        var parts: [String] = []
        if let started = notes.started {
            parts.append(started.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).hour().minute()))
        }
        if notes.duration > 0 { parts.append(MeetingModel.length(notes.duration)) }
        if !notes.app.isEmpty { parts.append(notes.app) }
        if !notes.people.isEmpty {
            parts.append("with " + ListFormatter.localizedString(byJoining: notes.people))
        }
        return parts.joined(separator: " · ")
    }
}

/// Notes, To-dos and Transcript, under the header.
struct TabStrip: View {
    @Environment(\.miloTheme) private var theme
    @Binding var tab: MeetingPage.Tab
    let todos: Int
    let lines: Int
    @Namespace private var underline

    var body: some View {
        HStack(spacing: 18) {
            ForEach(MeetingPage.Tab.allCases, id: \.self) { item in
                Button { tab = item } label: {
                    VStack(spacing: 6) {
                        HStack(spacing: 5) {
                            Text(item.rawValue)
                            if item == .todos && todos > 0 { count(todos) }
                        }
                        .font(.system(size: 13, weight: tab == item ? .semibold : .medium, design: .rounded))
                        .foregroundStyle(tab == item ? theme.ink : theme.ink.opacity(0.55))
                        ZStack {
                            if tab == item {
                                Capsule().fill(theme.primary).frame(height: 2.5)
                                    .matchedGeometryEffect(id: "tab", in: underline)
                            } else {
                                Capsule().fill(.clear).frame(height: 2.5)
                            }
                        }
                    }
                    .fixedSize()
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(tab == item ? .isSelected : [])
            }
            Spacer()
        }
        .padding(.horizontal, 22)
        .animation(theme.motion.spring, value: tab)
        .overlay(alignment: .bottom) { Rectangle().fill(theme.rule).frame(height: 1) }
    }

    private func count(_ n: Int) -> some View {
        Text("\(n)")
            .font(.system(size: 10.5, weight: .bold, design: .rounded).monospacedDigit())
            .foregroundStyle(theme.onPrimary)
            .padding(.horizontal, 5.5)
            .padding(.vertical, 1)
            .background(Capsule().fill(theme.accent))
    }
}

/// The to-dos from a meeting, each with "Add to Reminders", the user's own first.
struct TodoList: View {
    @Environment(\.miloTheme) private var theme
    let notes: MeetingNotes
    let add: (Int?) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                if notes.todos.isEmpty {
                    Text("Nobody took on anything in this one.")
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink.opacity(0.55))
                } else if notes.reminders, notes.todos.filter({ $0.mine && !$0.added }).count > 1 {
                    Button("Add all of mine to Reminders") { add(nil) }
                        .buttonStyle(PageButtonStyle(prominent: true))
                }
                ForEach(order, id: \.self) { index in
                    row(index, notes.todos[index])
                }
            }
            .padding(.horizontal, 22)
            .padding(.vertical, 18)
            .frame(maxWidth: 680, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var order: [Int] {
        notes.todos.indices.sorted { a, b in
            notes.todos[a].mine != notes.todos[b].mine ? notes.todos[a].mine : a < b
        }
    }

    private func row(_ index: Int, _ todo: MeetingNotes.Todo) -> some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: todo.added ? "checkmark.circle.fill" : "circle")
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(todo.added ? theme.primary : theme.ink.opacity(0.35))
            VStack(alignment: .leading, spacing: 2) {
                Text(todo.text)
                    .font(.system(size: 13.5, weight: .medium))
                    .foregroundStyle(theme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                let who = todo.mine ? "You" : todo.owner.isEmpty ? "Nobody yet" : todo.owner
                Text(todo.due.isEmpty ? who : "\(who) · \(todo.due)")
                    .font(.system(size: 11.5))
                    .foregroundStyle(todo.mine ? theme.primary : theme.ink.opacity(0.55))
            }
            Spacer(minLength: 8)
            if todo.added {
                Text("In Reminders")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.5))
            } else if notes.reminders {
                Button("Add to Reminders") { add(index) }
                    .buttonStyle(PageButtonStyle(prominent: false))
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(theme.rule))
        .accessibilityElement(children: .contain)
    }
}

/// A button on a page: filled in Milo's colour, or a soft one beside it.
struct PageButtonStyle: ButtonStyle {
    @Environment(\.miloTheme) private var theme
    @Environment(\.isEnabled) private var enabled
    let prominent: Bool
    @State private var hovered = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12.5, weight: .semibold, design: .rounded))
            .foregroundStyle(prominent ? theme.onPrimary : theme.ink.opacity(enabled ? 0.85 : 0.5))
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, 12)
            .frame(height: 30)
            .background(Capsule(style: .continuous)
                .fill(prominent ? theme.primary : theme.ink.opacity(hovered && enabled ? 0.11 : 0.065)))
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(theme.motion.spring, value: configuration.isPressed)
            .contentShape(Capsule())
            .onHover { hovered = $0 }
    }
}
