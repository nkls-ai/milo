import Foundation
import Combine

/// The conversation the Milo window shows, built from `history`, `entry`, `reply_delta` and `activity`.
/// Updated on the main queue.
public final class TranscriptModel: ObservableObject {
    /// The window keeps at most this many entries; the brain sends fewer on connect.
    public static let limit = 200

    @Published public private(set) var entries: [TranscriptEntry] = []

    public init(entries: [TranscriptEntry] = []) {
        self.entries = entries
    }

    public func apply(_ event: BrainEvent) {
        switch event {
        case let .history(list):
            entries = Array(list.suffix(Self.limit))
        case let .entry(entry):
            if let i = index(of: entry.id) { entries[i] = entry } else { append(entry) }
        case let .replyDelta(id, text):
            if let i = index(of: id) {
                entries[i].text += text
            } else {
                append(TranscriptEntry(id: id, date: Date(), kind: .milo, text: text, done: false))
            }
        case let .activity(taskID, step):
            guard let i = index(of: taskID) else { return }
            if let j = entries[i].steps.firstIndex(where: { $0.id == step.id }) {
                entries[i].steps[j] = step
            } else {
                entries[i].steps.append(step)
            }
        default:
            break
        }
    }

    private func index(of id: String) -> Int? {
        entries.lastIndex(where: { $0.id == id })
    }

    private func append(_ entry: TranscriptEntry) {
        entries.append(entry)
        if entries.count > Self.limit { entries.removeFirst(entries.count - Self.limit) }
    }
}
