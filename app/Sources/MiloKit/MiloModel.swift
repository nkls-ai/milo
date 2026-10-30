import Foundation
import Combine

/// Everything the character view draws. Updated on the main queue.
public final class MiloModel: ObservableObject {
    @Published public var state: MiloState = .idle
    @Published public var emotion: Emotion = .neutral
    @Published public var bubble: String?
    @Published public var heard: String?
    @Published public var level: Double = 0
    @Published public var connected = false
    @Published public var drowsy = false
    /// Live transcript of the recording in progress, shown next to Milo.
    @Published public var partial: String?
    /// The mode a double tap locked on (hands-free), set by the controller.
    @Published public var handsFree: ListenMode?
    /// How Milo looks, from the brain's `ui_config`.
    @Published public var character: CharacterStyle = .pip
    /// A point on screen Milo should fly to and point at; nil sends him home to his corner.
    /// Global screen coordinates with the origin at the top-left of the main display and y down,
    /// the same as CGEvent locations and screenshots.
    @Published public var flyTarget: CGPoint?
    /// Where he is on the way, set by the overlay panel that moves him.
    @Published public internal(set) var flight: Flight = .perched

    private let scheduler: Scheduler
    private var hideBubble: ScheduledTask?

    public init(scheduler: Scheduler) {
        self.scheduler = scheduler
    }

    /// How long a bubble stays up: longer for longer text, at most 20 s.
    public static func bubbleDuration(for text: String) -> TimeInterval {
        min(20, 4 + Double(text.count) / 15)
    }

    /// Applies a display event. Dictation, ui_config and unknown events are not the model's business.
    public func apply(_ event: BrainEvent) {
        switch event {
        case let .state(new):
            state = new
            if state == .listening || state == .dictating { heard = nil }
            // A new question replaces the last answer, so that answer's hide timer can't later
            // wipe the new `heard` while Milo thinks.
            if state == .listening { bubble = nil }
            // Idle starts the hide timer; speaking and listening stop a pending one.
            if state == .idle || state == .speaking || state == .listening { scheduleBubbleHide() }
            if state != .speaking && state != .listening && state != .dictating { level = 0 }
            // A new recording starts empty; the last words stay up while the final pass runs.
            if state != .transcribing { partial = nil }
        case let .emotion(new):
            emotion = new
        case let .bubble(text), let .status(text):
            show(text)
        case let .heard(text):
            heard = text
        case let .level(value):
            level = value
        case let .partial(text):
            partial = text.isEmpty ? nil : text
        case .dictation, .uiConfig, .history, .entry, .replyDelta, .activity, .unknown:
            break
        }
    }

    /// Shows text in the bubble for a while. Empty text hides it.
    public func show(_ text: String) {
        bubble = text.isEmpty ? nil : text
        scheduleBubbleHide()
    }

    private func scheduleBubbleHide() {
        hideBubble?.cancel()
        hideBubble = nil
        guard let text = bubble, state != .speaking else { return }
        hideBubble = scheduler.after(Self.bubbleDuration(for: text)) { [weak self] in
            guard let self else { return }
            bubble = nil
            heard = nil
            if state == .idle { emotion = .neutral }
        }
    }
}
