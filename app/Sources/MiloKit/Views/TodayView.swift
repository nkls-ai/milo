import SwiftUI

/// Home: what Milo is doing now, what waits for you, today's reminders, what got done, and where you left off.
struct TodayView: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var transcript: TranscriptModel
    @ObservedObject var model: MiloModel
    @ObservedObject var route: WindowRoute
    let talkKey: String
    let actions: WindowActions
    let changeDraft: (RoutineDraft) -> Void
    @AppStorage("showRoutines") private var showRoutines = false
    @State private var shown = false
    /// Cards float in one after another; off for offscreen renders.
    static var entrance = true

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                header.card(0, shown).padding(.bottom, 4)
                if quiet {
                    calm.card(1, shown)
                } else {
                    let cards = sections
                    ForEach(Array(cards.enumerated()), id: \.offset) { i, card in
                        card.card(i + 1, shown)
                    }
                }
            }
            .padding(.horizontal, 24)
            .padding(.top, 22)
            .padding(.bottom, 24)
            .frame(maxWidth: 620, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .environment(\.todayMotion, Self.entrance && !reduceMotion ? theme.motion.spring : nil)
        .onAppear { shown = true }
    }

    /// Nothing at work, nothing waiting, no reminders, nothing done today.
    private var quiet: Bool {
        working.isEmpty && model.question == nil && model.drafts.isEmpty && transcript.reminders.isEmpty
            && doneToday.isEmpty && lastConversation == nil && meetings.isEmpty
    }

    private var sections: [AnyView] {
        var cards: [AnyView] = []
        if model.question != nil || !model.drafts.isEmpty { cards.append(AnyView(waiting)) }
        if !working.isEmpty { cards.append(AnyView(workingCard)) }
        if !transcript.reminders.isEmpty { cards.append(AnyView(remindersCard)) }
        if !doneToday.isEmpty { cards.append(AnyView(doneCard)) }
        if !meetings.isEmpty { cards.append(AnyView(meetingsCard)) }
        if let last = lastConversation { cards.append(AnyView(pickUp(last))) }
        if !model.routines.isEmpty {
            cards.append(AnyView(RoutinesPanel(routines: model.routines, open: $showRoutines, act: model.routine)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))))
        }
        return cards
    }

    // ---- the parts

    private var header: some View {
        HStack(alignment: .center, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text(ConversationsSidebar.now().formatted(.dateTime.weekday(.wide).day().month(.wide)))
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.primary)
                Text(greeting)
                    .font(.system(size: 24, weight: .bold, design: .rounded))
                    .foregroundStyle(theme.ink)
                Text(summary)
                    .font(.system(size: 12.5))
                    .foregroundStyle(theme.ink.opacity(0.58))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 8)
            CharacterFigure(for: theme.style, emotion: model.question != nil ? .thinking : working.isEmpty ? .happy : .excited,
                            size: 58)
                .frame(width: 58, height: 58)
                .background(Circle().fill(RadialGradient(colors: [theme.glow.opacity(0.5), theme.glow.opacity(0)],
                                                         center: .center, startRadius: 4, endRadius: 46))
                    .frame(width: 96, height: 96))
                .accessibilityHidden(true)
        }
    }

    private var calm: some View {
        VStack(spacing: 10) {
            Image(systemName: "leaf")
                .font(.system(size: 22, weight: .medium))
                .foregroundStyle(theme.primary.opacity(0.7))
            Text("Nothing on your plate.")
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .foregroundStyle(theme.ink)
            Text("Hold \(talkKey) and talk to Milo, or type below. What you ask for, and what he does, shows up here.")
                .font(.system(size: 12))
                .foregroundStyle(theme.ink.opacity(0.58))
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 34)
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous)
            .strokeBorder(theme.primary.opacity(0.2), style: StrokeStyle(lineWidth: 1.2, dash: [5, 5])))
    }

    private var waiting: some View {
        TodayCard(title: "Waiting for you", icon: "hand.raised.fill", tint: theme.accent) {
            if let question = model.question {
                HStack(alignment: .center, spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(question.text)
                            .font(.system(size: 13.5, weight: .medium, design: .rounded))
                            .foregroundStyle(theme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Or hold \(talkKey) and say yes or no.")
                            .font(.system(size: 11))
                            .foregroundStyle(theme.ink.opacity(0.5))
                    }
                    Spacer(minLength: 8)
                    AnswerButtons(choices: question.choices, answer: model.answer, choose: model.answer)
                }
            }
            ForEach(model.drafts) { draft in
                DraftCard(draft: draft, talkKey: talkKey, save: { model.answerDraft(draft.id, save: true) },
                          change: { changeDraft(draft) }, drop: { model.answerDraft(draft.id, save: false) })
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
        }
    }

    private var workingCard: some View {
        TodayCard(title: working.count == 1 ? "Milo is working on" : "Milo is working on \(working.count) things",
                  icon: "sparkles", tint: WindowColors.running) {
            ForEach(working) { helper in
                HelperRow(helper: helper, steps: [],
                          open: { route.go(.task(helper.id)) }, stop: { model.stopHelper(helper.id) })
            }
            if working.count > 1 {
                Button("Stop all") { working.forEach { model.stopHelper($0.id) } }
                    .buttonStyle(.plain)
                    .font(.system(size: 11.5, weight: .medium, design: .rounded))
                    .foregroundStyle(WindowColors.failed)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
    }

    private var remindersCard: some View {
        TodayCard(title: "Reminders", icon: "bell.fill", tint: theme.primary) {
            ForEach(Array(transcript.reminders.enumerated()), id: \.offset) { _, reminder in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(Self.due(reminder.due))
                        .font(.system(size: 11.5, weight: .semibold, design: .rounded).monospacedDigit())
                        .foregroundStyle(reminder.due < ConversationsSidebar.now() ? theme.accent : theme.primary)
                        .frame(width: 74, alignment: .leading)
                    Text(reminder.text)
                        .font(.system(size: 13))
                        .foregroundStyle(theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var doneCard: some View {
        TodayCard(title: "Done today", icon: "checkmark.seal.fill", tint: WindowColors.done) {
            ForEach(doneToday, id: \.task.id) { item in
                Button { actions.open(item.conversation.id); route.go(.task(item.task.id)) } label: {
                    HStack(spacing: 10) {
                        StatusSeal(status: item.task.status, size: 20)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(item.task.title)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(theme.ink)
                                .lineLimit(1)
                            Text("in “\(item.conversation.title)”")
                                .font(.system(size: 11))
                                .foregroundStyle(theme.ink.opacity(0.5))
                                .lineLimit(1)
                        }
                        Spacer(minLength: 6)
                        Text(item.task.date.formatted(date: .omitted, time: .shortened))
                            .font(.system(size: 10.5).monospacedDigit())
                            .foregroundStyle(theme.ink.opacity(0.42))
                        Image(systemName: "chevron.right")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(theme.ink.opacity(0.3))
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// This week's meetings, the one going on first: each opens its notes, or its live transcript.
    private var meetingsCard: some View {
        TodayCard(title: "Meetings", icon: "person.2.fill", tint: theme.accent) {
            ForEach(meetings) { conversation in
                let live = model.meeting.status.conversation == conversation.id && model.meeting.status.phase != .done
                    && model.meeting.status.phase != .none
                Button { actions.open(conversation.id); route.go(.conversation(conversation.id)) } label: {
                    HStack(spacing: 10) {
                        ZStack {
                            if live { LiveLight(paused: model.meeting.status.phase == .paused) } else {
                                Image(systemName: "note.text")
                                    .font(.system(size: 11, weight: .semibold))
                                    .foregroundStyle(theme.accent)
                            }
                        }
                        .frame(width: 20, height: 20)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(conversation.title)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(theme.ink)
                                .lineLimit(1)
                            Text(live ? (model.meeting.status.phase == .writing ? "Writing the notes…" : "Taking notes now")
                                      : MeetingPageID.summary(of: conversation.preview))
                                .font(.system(size: 11))
                                .foregroundStyle(theme.ink.opacity(live ? 0.7 : 0.5))
                                .lineLimit(1)
                        }
                        Spacer(minLength: 6)
                        Text(DayGroups.time(conversation.started, now: ConversationsSidebar.now()))
                            .font(.system(size: 10.5).monospacedDigit())
                            .foregroundStyle(theme.ink.opacity(0.42))
                        Image(systemName: "chevron.right")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(theme.ink.opacity(0.3))
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint(live ? "Opens the live transcript" : "Opens the notes")
            }
        }
    }

    private func pickUp(_ conversation: ConversationInfo) -> some View {
        Button {
            if conversation.id == transcript.current { route.go(.live) } else {
                actions.open(conversation.id)
                route.go(.conversation(conversation.id))
            }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: "arrow.uturn.backward")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(theme.primary)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(theme.primary.opacity(0.12)))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Pick up where you left off")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(theme.ink.opacity(0.5))
                    HStack(spacing: 5) {
                        KindMark(conversation: conversation)
                        Text(conversation.title)
                            .font(.system(size: 13.5, weight: .semibold, design: .rounded))
                            .foregroundStyle(theme.ink)
                            .lineLimit(1)
                    }
                    if !conversation.preview.isEmpty {
                        Text(conversation.preview)
                            .font(.system(size: 11.5))
                            .foregroundStyle(theme.ink.opacity(0.55))
                            .lineLimit(1)
                    }
                }
                Spacer(minLength: 6)
                Text(DayGroups.time(conversation.last, now: ConversationsSidebar.now()))
                    .font(.system(size: 10.5).monospacedDigit())
                    .foregroundStyle(theme.ink.opacity(0.42))
            }
            .padding(14)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(theme.card))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // ---- what goes in

    private var working: [HelperInfo] { model.helpers.filter(\.status.active) }

    private var doneToday: [(task: TaskSummary, conversation: ConversationInfo)] {
        let calendar = Calendar.current
        let now = ConversationsSidebar.now()
        return transcript.conversations.flatMap { c in
            c.tasks.filter { $0.status != .running && calendar.isDate($0.date, inSameDayAs: now) }.map { ($0, c) }
        }
        .sorted { $0.task.date > $1.task.date }
        .prefix(5).map { $0 }
    }

    /// Meetings of the last seven days, newest first, at most four.
    private var meetings: [ConversationInfo] {
        let since = ConversationsSidebar.now().addingTimeInterval(-7 * 86400)
        return Array(transcript.conversations.filter { $0.kind == .meeting && $0.started >= since }
            .sorted { $0.started > $1.started }.prefix(4))
    }

    private var lastConversation: ConversationInfo? {
        transcript.conversations.first { $0.kind == .chat }
    }

    private var greeting: String {
        let hour = Calendar.current.component(.hour, from: ConversationsSidebar.now())
        switch hour {
        case 5..<12: return "Good morning."
        case 12..<18: return "Good afternoon."
        case 18..<23: return "Good evening."
        default: return "Still up?"
        }
    }

    /// One quiet line under the greeting: "Waiting for your answer · 1 thing in progress · 2 done today".
    private var summary: String {
        var parts: [String] = []
        if model.question != nil || !model.drafts.isEmpty { parts.append("Waiting for your answer") }
        if !working.isEmpty { parts.append(working.count == 1 ? "1 thing in progress" : "\(working.count) things in progress") }
        if !doneToday.isEmpty { parts.append("\(doneToday.count) done today") }
        return parts.isEmpty ? "Here's your day with Milo." : parts.joined(separator: " · ")
    }

    static func due(_ date: Date, now: Date = ConversationsSidebar.now()) -> String {
        let time = date.formatted(date: .omitted, time: .shortened)
        return Calendar.current.isDate(date, inSameDayAs: now) ? time : "Tmrw \(time)"
    }
}

/// A Today section: a small coloured heading and its rows on a card.
struct TodayCard<Content: View>: View {
    @Environment(\.miloTheme) private var theme
    let title: String
    let icon: String
    let tint: Color
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .font(.system(size: 10.5, weight: .bold))
                    .foregroundStyle(tint)
                    .frame(width: 20, height: 20)
                    .background(Circle().fill(tint.opacity(0.15)))
                Text(title)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.7))
            }
            VStack(alignment: .leading, spacing: 10) { content }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(theme.rule, lineWidth: 1))
        .shadow(color: theme.primary.opacity(0.06), radius: 10, y: 3)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(title)
    }
}

private struct TodayMotionKey: EnvironmentKey {
    static let defaultValue: Animation? = nil
}

extension EnvironmentValues {
    /// The spring Today's cards float in with; nil shows them at once.
    var todayMotion: Animation? {
        get { self[TodayMotionKey.self] }
        set { self[TodayMotionKey.self] = newValue }
    }
}

private struct Entrance: ViewModifier {
    @Environment(\.todayMotion) private var motion
    let index: Int
    let shown: Bool

    func body(content: Content) -> some View {
        let hidden = motion != nil && !shown
        content
            .opacity(hidden ? 0 : 1)
            .offset(y: hidden ? 10 : 0)
            .animation(motion?.delay(Double(index) * 0.05), value: shown)
    }
}

extension View {
    /// The `index`th card of Today, floating in once `shown`.
    fileprivate func card(_ index: Int, _ shown: Bool) -> some View {
        modifier(Entrance(index: index, shown: shown))
    }
}
