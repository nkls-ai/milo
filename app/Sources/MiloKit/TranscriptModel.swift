import Foundation
import Combine

/// What the Milo window shows: the conversations, the one going on with its entries as they stream, the ones the
/// user opened, search results and today's reminders. Built from `conversations`, `conversation`, `history`,
/// `entry`, `reply_delta`, `activity`, `search_results` and `reminders`. Updated on the main queue.
/// See docs/design/conversations.md.
public final class TranscriptModel: ObservableObject {
    /// The window keeps at most this many entries per conversation; the brain sends fewer on connect.
    public static let limit = 200

    /// The current conversation's entries, oldest first.
    @Published public private(set) var entries: [TranscriptEntry] = []
    /// Every conversation the brain listed, latest first.
    @Published public private(set) var conversations: [ConversationInfo] = []
    /// The id of the conversation going on; "" when none is.
    @Published public private(set) var current = ""
    /// Older conversations exist than the list holds.
    @Published public private(set) var more = false
    /// Entries of conversations the user opened (and of the current one before a split), by id.
    @Published public private(set) var opened: [String: [TranscriptEntry]] = [:]
    @Published public private(set) var searchQuery = ""
    @Published public private(set) var searchResults: [SearchHit] = []
    @Published public private(set) var reminders: [ReminderItem] = []

    public init(entries: [TranscriptEntry] = [], conversations: [ConversationInfo] = [], current: String? = nil,
                opened: [String: [TranscriptEntry]] = [:], reminders: [ReminderItem] = []) {
        self.entries = entries
        self.conversations = conversations
        self.current = current ?? entries.last?.conversation ?? ""
        self.opened = opened
        self.reminders = reminders
    }

    public func info(_ id: String) -> ConversationInfo? {
        conversations.first { $0.id == id }
    }

    /// A conversation's entries as far as the window has them.
    public func entries(of id: String) -> [TranscriptEntry] {
        id == current ? entries : opened[id] ?? []
    }

    /// A task entry wherever it is, and the conversation that asked for it.
    public func task(_ id: String) -> (entry: TranscriptEntry, conversation: ConversationInfo?)? {
        if let entry = entries.last(where: { $0.id == id }) { return (entry, info(entry.conversation.isEmpty ? current : entry.conversation)) }
        for (conversation, list) in opened {
            if let entry = list.last(where: { $0.id == id }) { return (entry, info(conversation)) }
        }
        return nil
    }

    /// The conversation a task belongs to, from the headers, for a task the window hasn't loaded yet.
    public func conversation(ofTask id: String) -> ConversationInfo? {
        conversations.first { $0.tasks.contains { $0.id == id } }
    }

    public func apply(_ event: BrainEvent) {
        switch event {
        case let .history(list):
            if let id = list.last?.conversation, !id.isEmpty, id != current { switchCurrent(to: id) }
            entries = Array(list.suffix(Self.limit))
        case let .entry(entry):
            upsert(entry)
        case let .replyDelta(id, text):
            if let i = index(of: id) {
                entries[i].text += text
            } else if let (conversation, j) = openedIndex(of: id) {
                opened[conversation]?[j].text += text
            } else {
                append(TranscriptEntry(id: id, date: Date(), kind: .milo, text: text, done: false, conversation: current))
            }
        case let .activity(taskID, step):
            if let i = index(of: taskID) {
                entries[i].steps.upsert(step)
            } else if let (conversation, j) = openedIndex(of: taskID) {
                opened[conversation]?[j].steps.upsert(step)
            }
        case let .conversations(list, current, more):
            conversations = list
            self.more = more
            if current != self.current { switchCurrent(to: current) }
        case let .conversation(info, list):
            if let i = conversations.firstIndex(where: { $0.id == info.id }) {
                conversations[i] = info
            } else {
                conversations.append(info)
                conversations.sort { $0.last > $1.last }
            }
            if info.id == current {
                // Keep what streams right now; the brain's copy has the rest.
                let live = entries.filter { e in !list.contains { $0.id == e.id } }
                entries = (list + live).sorted { $0.date < $1.date }.suffix(Self.limit).map { $0 }
            } else {
                opened[info.id] = Array(list.suffix(Self.limit))
            }
        case let .searchResults(query, results):
            searchQuery = query
            searchResults = results
        case let .reminders(list):
            reminders = list
        default:
            break
        }
    }

    /// The window cleared its search field.
    public func clearSearch() {
        searchQuery = ""
        searchResults = []
    }

    /// A new user turn in a conversation the window doesn't know yet starts the next one: the brain's list,
    /// which says so too, comes a moment later.
    private func upsert(_ entry: TranscriptEntry) {
        let id = entry.conversation
        if id.isEmpty || id == current {
            if let i = index(of: entry.id) { entries[i] = entry } else { append(entry) }
            return
        }
        let known = conversations.contains { $0.id == id } || opened[id] != nil
        if !known && entry.kind == .user {
            switchCurrent(to: id)
            append(entry)
            return
        }
        var list = opened[id] ?? []
        if let j = list.lastIndex(where: { $0.id == entry.id }) { list[j] = entry } else { list.append(entry) }
        opened[id] = list
    }

    private func switchCurrent(to id: String) {
        if !current.isEmpty { opened[current] = entries }
        current = id
        entries = opened.removeValue(forKey: id) ?? []
    }

    private func index(of id: String) -> Int? {
        entries.lastIndex(where: { $0.id == id })
    }

    private func openedIndex(of id: String) -> (String, Int)? {
        for (conversation, list) in opened {
            if let j = list.lastIndex(where: { $0.id == id }) { return (conversation, j) }
        }
        return nil
    }

    private func append(_ entry: TranscriptEntry) {
        entries.append(entry)
        if entries.count > Self.limit { entries.removeFirst(entries.count - Self.limit) }
    }
}

extension [ActivityStep] {
    mutating func upsert(_ step: ActivityStep) {
        if let j = firstIndex(where: { $0.id == step.id }) { self[j] = step } else { append(step) }
    }
}
