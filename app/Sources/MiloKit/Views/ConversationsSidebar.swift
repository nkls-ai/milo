import SwiftUI

/// The Milo window's left side: search, Today, and the conversations by day, each hanging on a thread with a bead
/// like a task's steps. The conversation going on breathes. A selected row is a card that glides to it.
struct ConversationsSidebar: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ObservedObject var transcript: TranscriptModel
    @ObservedObject var route: WindowRoute
    let waiting: Int
    let actions: WindowActions
    var searchFocus: FocusState<Bool>.Binding
    @Namespace private var selection
    /// The time the rows are drawn against, for offscreen renders.
    static var now: () -> Date = Date.init

    var body: some View {
        VStack(spacing: 0) {
            SearchField(text: $route.search, focus: searchFocus, submit: openFirst)
                .padding(.horizontal, 12)
                .padding(.top, 12)
                .padding(.bottom, 8)
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if route.search.trimmingCharacters(in: .whitespaces).isEmpty {
                        todayRow.padding(.bottom, 6)
                        list
                    } else {
                        results
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 12)
                .animation(theme.motion.animation(reduced: reduceMotion), value: transcript.conversations.map(\.id))
            }
            newButton
        }
        .background(theme.ink.opacity(0.035))
        .background(theme.tint)
    }

    // ---- Today and the list

    private var todayRow: some View {
        SidebarButton(selected: route.page == .today, namespace: selection) {
            route.go(.today)
        } label: {
            HStack(spacing: 9) {
                Image(systemName: "sun.max.fill")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(theme.accent)
                    .frame(width: 18)
                Text("Today")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink)
                Spacer(minLength: 4)
                if waiting > 0 {
                    Text("\(waiting)")
                        .font(.system(size: 10.5, weight: .bold, design: .rounded).monospacedDigit())
                        .foregroundStyle(theme.onPrimary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 1.5)
                        .background(Capsule().fill(theme.accent))
                        .help(waiting == 1 ? "Milo waits for you" : "\(waiting) things wait for you")
                }
                KeyHint("⌘1")
            }
            .padding(.vertical, 7)
            .padding(.horizontal, 8)
        }
        .accessibilityLabel(waiting > 0 ? "Today, \(waiting) waiting for you" : "Today")
    }

    @ViewBuilder private var list: some View {
        let groups = DayGroups.group(transcript.conversations, now: Self.now())
        if groups.isEmpty {
            Text("Your conversations with Milo show up here, one for each thing you talk about.")
                .font(.system(size: 11.5))
                .foregroundStyle(theme.ink.opacity(0.5))
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 10)
                .padding(.top, 14)
        }
        ForEach(groups, id: \.title) { group in
            Text(group.title.uppercased())
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .tracking(0.8)
                .foregroundStyle(theme.ink.opacity(0.42))
                .padding(.leading, 10)
                .padding(.top, 12)
                .padding(.bottom, 4)
            ForEach(Array(group.items.enumerated()), id: \.element.id) { i, conversation in
                row(conversation, first: i == 0, last: i == group.items.count - 1)
                    .transition(.asymmetric(insertion: .move(edge: .top).combined(with: .opacity), removal: .opacity))
            }
        }
        if transcript.more, let oldest = transcript.conversations.last {
            Button("Show older") { actions.older(TranscriptModel.wire(oldest.last)) }
                .buttonStyle(.plain)
                .font(.system(size: 11.5, weight: .medium, design: .rounded))
                .foregroundStyle(theme.primary)
                .padding(.leading, 30)
                .padding(.top, 8)
        }
    }

    private func row(_ conversation: ConversationInfo, first: Bool, last: Bool) -> some View {
        let live = conversation.id == transcript.current
        let selected = route.page == .conversation(conversation.id) || (live && route.page == .live)
        return SidebarButton(selected: selected, namespace: selection) {
            if live { route.go(.live) } else {
                actions.open(conversation.id)
                route.go(.conversation(conversation.id))
            }
        } label: {
            ConversationRow(conversation: conversation, live: live, selected: selected, first: first, last: last,
                            now: Self.now())
        }
        .contextMenu {
            Button("Open") { actions.open(conversation.id); route.go(.conversation(conversation.id)) }
        }
    }

    // ---- search

    @ViewBuilder private var results: some View {
        let query = route.search.trimmingCharacters(in: .whitespaces)
        if transcript.searchQuery != query {
            HStack(spacing: 8) {
                ThinkingDots(color: theme.accent).scaleEffect(0.5).frame(width: 16, height: 10)
                Text("Looking…").font(.system(size: 12)).foregroundStyle(theme.ink.opacity(0.55))
            }
            .padding(.horizontal, 10)
            .padding(.top, 10)
        } else if transcript.searchResults.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text("Nothing about “\(query)”.")
                    .font(.system(size: 12.5, weight: .medium, design: .rounded))
                    .foregroundStyle(theme.ink.opacity(0.75))
                Text("Try other words: Milo also looks by meaning.")
                    .font(.system(size: 11.5))
                    .foregroundStyle(theme.ink.opacity(0.5))
            }
            .padding(.horizontal, 10)
            .padding(.top, 10)
        } else {
            Text(transcript.searchResults.count == 1 ? "1 CONVERSATION" : "\(transcript.searchResults.count) CONVERSATIONS")
                .font(.system(size: 10, weight: .bold, design: .rounded))
                .tracking(0.8)
                .foregroundStyle(theme.ink.opacity(0.42))
                .padding(.leading, 10)
                .padding(.top, 6)
                .padding(.bottom, 4)
            ForEach(transcript.searchResults) { hit in
                let selected = route.page == .conversation(hit.conversation)
                SidebarButton(selected: selected, namespace: selection) {
                    actions.open(hit.conversation)
                    route.go(hit.conversation == transcript.current ? .live : .conversation(hit.conversation))
                } label: {
                    SearchRow(hit: hit, query: query, now: Self.now())
                }
            }
        }
    }

    private func openFirst() {
        guard let hit = transcript.searchResults.first, transcript.searchQuery == route.search.trimmingCharacters(in: .whitespaces)
        else { return }
        actions.open(hit.conversation)
        route.go(hit.conversation == transcript.current ? .live : .conversation(hit.conversation))
    }

    private var newButton: some View {
        Button {
            actions.newConversation()
            route.go(.live)
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "plus")
                    .font(.system(size: 11, weight: .bold))
                    .frame(width: 18, height: 18)
                    .background(Circle().fill(theme.primary.opacity(0.14)))
                Text("New conversation")
                    .font(.system(size: 12.5, weight: .semibold, design: .rounded))
                Spacer()
                KeyHint("⌘N")
            }
            .foregroundStyle(theme.primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(alignment: .top) { Rectangle().fill(theme.rule).frame(height: 1) }
        .help("Start fresh: Milo forgets the last few minutes for this one")
    }
}

/// A row button whose selection is a soft card that glides from row to row.
struct SidebarButton<Label: View>: View {
    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let selected: Bool
    let namespace: Namespace.ID
    let action: () -> Void
    @ViewBuilder let label: Label
    @State private var hovered = false

    var body: some View {
        Button {
            withAnimation(theme.motion.animation(reduced: reduceMotion)) { action() }
        } label: {
            label
                .background {
                    if selected {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(theme.card)
                            .shadow(color: theme.primary.opacity(0.12), radius: 6, y: 2)
                            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .strokeBorder(theme.primary.opacity(0.18), lineWidth: 1))
                            .matchedGeometryEffect(id: "selection", in: namespace)
                    } else if hovered {
                        RoundedRectangle(cornerRadius: 10, style: .continuous).fill(theme.ink.opacity(0.045))
                    }
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// One conversation in the list: its bead on the thread, the title, a line of preview and the time.
struct ConversationRow: View {
    @Environment(\.miloTheme) private var theme
    let conversation: ConversationInfo
    let live: Bool
    let selected: Bool
    let first: Bool
    let last: Bool
    let now: Date

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            ThreadBead(state: beadState, selected: selected)
                .padding(.top, Self.bead - 5.5)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 5) {
                    KindMark(conversation: conversation)
                    Text(conversation.title.isEmpty ? "A conversation" : conversation.title)
                        .font(.system(size: 12.5, weight: selected || live ? .semibold : .medium, design: .rounded))
                        .foregroundStyle(theme.ink)
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Text(DayGroups.time(conversation.last, now: now))
                        .font(.system(size: 10.5).monospacedDigit())
                        .foregroundStyle(theme.ink.opacity(0.42))
                        .layoutPriority(1)
                }
                Text(subtitle)
                    .font(.system(size: 11.5))
                    .foregroundStyle(theme.ink.opacity(live && conversation.working ? 0.7 : 0.52))
                    .lineLimit(1)
            }
            .padding(.vertical, 7)
            .padding(.trailing, 8)
        }
        .padding(.leading, 8)
        .background(alignment: .leading) { thread.frame(width: 18).padding(.leading, 8) }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibility)
    }

    /// The bead's centre from the top of the row, level with the title.
    static let bead: CGFloat = 15.5

    private var beadState: ThreadBead.State {
        if conversation.working { return .working }
        if live { return .live }
        return conversation.tasks.contains { $0.status == .failed } ? .failed : .rest
    }

    /// The thread runs through the group, bead to bead: from the row above to the row below.
    private var thread: some View {
        VStack(spacing: 0) {
            Rectangle().opacity(first ? 0 : 1).frame(height: Self.bead)
            Rectangle().opacity(last ? 0 : 1)
        }
        .foregroundStyle(theme.primary.opacity(0.2))
        .frame(width: 1.5)
    }

    private var subtitle: String {
        if let running = conversation.tasks.last(where: { $0.status == .running }) {
            return running.title == conversation.title ? "Working on it…" : "Working on “\(running.title)”…"
        }
        if !conversation.preview.isEmpty { return conversation.preview }
        switch conversation.kind {
        case .meeting: return "Meeting notes"
        case .routine: return "Ran on its schedule"
        case .chat: return conversation.turns == 1 ? "1 message" : "\(conversation.turns) messages"
        }
    }

    private var accessibility: String {
        var parts = [conversation.title]
        if conversation.fromPhone { parts.append("from your phone") }
        if conversation.kind == .meeting { parts.append("meeting notes") }
        if conversation.kind == .routine { parts.append("routine") }
        if live { parts.append("going on now") }
        parts.append(subtitle)
        return parts.joined(separator: ", ")
    }
}

/// The small sign before a title: a phone, two people for a meeting, a loop for a routine.
struct KindMark: View {
    @Environment(\.miloTheme) private var theme
    let conversation: ConversationInfo

    var body: some View {
        if let symbol {
            Image(systemName: symbol)
                .font(.system(size: 9.5, weight: .semibold))
                .foregroundStyle(conversation.kind == .chat ? theme.ink.opacity(0.55) : theme.primary)
                .help(help)
        }
    }

    private var symbol: String? {
        switch conversation.kind {
        case .meeting: "person.2.fill"
        case .routine: "arrow.triangle.2.circlepath"
        case .chat: conversation.fromPhone ? "iphone" : nil
        }
    }

    private var help: String {
        switch conversation.kind {
        case .meeting: "Notes from a meeting"
        case .routine: "A routine that ran on its schedule"
        case .chat: "From your phone"
        }
    }
}

/// A conversation's bead: resting, the one going on (a ring that breathes), at work (marigold), or a task failed.
struct ThreadBead: View {
    enum State { case rest, live, working, failed }

    @Environment(\.miloTheme) private var theme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let state: State
    var selected = false
    @SwiftUI.State private var breathe = false

    var body: some View {
        ZStack {
            switch state {
            case .rest:
                Circle().fill(theme.card)
                Circle().strokeBorder(theme.primary.opacity(selected ? 0.9 : 0.45), lineWidth: 1.5)
                if selected { Circle().fill(theme.primary).padding(3.5) }
            case .live, .working:
                let color = state == .working ? WindowColors.running : theme.primary
                Circle().fill(color.opacity(0.22)).scaleEffect(breathe ? 1.55 : 1)
                    .opacity(breathe ? 0 : 1)
                Circle().fill(color)
                Circle().fill(theme.card).padding(3.5).opacity(state == .working ? 1 : 0)
            case .failed:
                Circle().fill(WindowColors.failed)
                Image(systemName: "exclamationmark").font(.system(size: 6.5, weight: .black)).foregroundStyle(.white)
            }
        }
        .frame(width: 11, height: 11)
        .onAppear {
            guard !reduceMotion, state == .live || state == .working else { return }
            withAnimation(.easeOut(duration: 1.6).repeatForever(autoreverses: false)) { breathe = true }
        }
        .accessibilityHidden(true)
    }
}

/// A search result: the title, where the words were found, and when.
struct SearchRow: View {
    @Environment(\.miloTheme) private var theme
    let hit: SearchHit
    let query: String
    let now: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 5) {
                KindMark(conversation: ConversationInfo(id: hit.conversation, kind: hit.kind, started: hit.date,
                                                        title: hit.title, via: hit.via))
                Text(hit.title).font(.system(size: 12.5, weight: .semibold, design: .rounded))
                    .foregroundStyle(theme.ink).lineLimit(1)
                Spacer(minLength: 4)
                Text(DayGroups.time(hit.date, now: now))
                    .font(.system(size: 10.5).monospacedDigit())
                    .foregroundStyle(theme.ink.opacity(0.42))
            }
            if !hit.snippet.isEmpty {
                Self.highlighted(hit.snippet, query, theme)
                    .font(.system(size: 11.5))
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 7)
        .padding(.horizontal, 10)
    }

    /// The snippet with the words searched for in Milo's colour.
    static func highlighted(_ text: String, _ query: String, _ theme: Theme) -> Text {
        var attributed = AttributedString(text)
        attributed.foregroundColor = theme.ink.opacity(0.6)
        for word in query.lowercased().split(separator: " ") where word.count > 1 {
            var start = attributed.startIndex
            while let range = attributed[start...].range(of: word, options: .caseInsensitive) {
                attributed[range].foregroundColor = theme.primary
                attributed[range].font = .system(size: 11.5, weight: .semibold)
                start = range.upperBound
            }
        }
        return Text(attributed)
    }
}

/// The search field: ⌘F, a magnifier, and Esc to clear.
struct SearchField: View {
    @Environment(\.miloTheme) private var theme
    @Binding var text: String
    var focus: FocusState<Bool>.Binding
    /// Enter: open the first result.
    var submit: () -> Void = {}

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(theme.ink.opacity(0.45))
            TextField("Search", text: $text)
                .textFieldStyle(.plain)
                .font(.system(size: 12.5))
                .focused(focus)
                .onSubmit(submit)
                .onExitCommand { text = ""; focus.wrappedValue = false }
            if text.isEmpty {
                KeyHint("⌘F")
            } else {
                Button { text = "" } label: {
                    Image(systemName: "xmark.circle.fill").font(.system(size: 11)).foregroundStyle(theme.ink.opacity(0.4))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear the search")
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: 9, style: .continuous).fill(theme.card))
        .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous)
            .strokeBorder(focus.wrappedValue ? theme.primary.opacity(0.5) : theme.rule, lineWidth: 1))
    }
}

/// A shortcut, quietly: "⌘N".
struct KeyHint: View {
    @Environment(\.miloTheme) private var theme
    let keys: String

    init(_ keys: String) { self.keys = keys }

    var body: some View {
        Text(keys)
            .font(.system(size: 9.5, weight: .medium, design: .rounded))
            .foregroundStyle(theme.ink.opacity(0.35))
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(RoundedRectangle(cornerRadius: 4, style: .continuous).strokeBorder(theme.ink.opacity(0.12)))
            .accessibilityHidden(true)
    }
}

extension TranscriptModel {
    /// A date as the brain writes local times, for `get_conversations before`.
    static func wire(_ date: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = .current
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f.string(from: date)
    }
}
