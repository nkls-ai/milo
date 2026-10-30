import Foundation
import Combine

/// A yes-or-no question Milo waits on before an action.
public struct PendingQuestion: Equatable, Sendable {
    public let id: String
    public let text: String

    public init(id: String, text: String) {
        self.id = id
        self.text = text
    }
}

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
    /// Milo is looking at the screen: a small eye shows on him.
    @Published public var looking = false
    /// The worker agent is acting on screen: the "Milo is working" frame shows.
    @Published public var handsActive = false
    /// The user lent Milo the real mouse and keyboard: the frame around the screen shows, and any touch stops him.
    @Published public var handsBorrowed = false
    /// The window Milo works in, in AppKit global coordinates: outlined, and Pip perches on its corner.
    @Published public var workingWindow: CGRect?
    /// How Milo looks, from the brain's `ui_config`.
    @Published public var character: CharacterStyle = .pip
    /// A point on screen Milo should fly to and point at, in AppKit global screen coordinates (points,
    /// origin bottom-left of the main display). nil sends him home to his corner.
    @Published public var flyTarget: CGPoint?
    /// Where he is on the way, set by the overlay panel that moves him.
    @Published public internal(set) var flight: Flight = .perched
    /// Shown with Yes and No in the bubble and the Milo window until answered or over.
    @Published public private(set) var question: PendingQuestion?
    /// Called with the user's click on Yes (true) or No. Set by the controller.
    public var onAnswer: ((PendingQuestion, Bool) -> Void)?
    /// The helpers working for Milo, oldest first, from the brain's `helpers` event.
    @Published public private(set) var helpers: [HelperInfo] = []
    /// Called when the user clicks Stop on a helper. Set by the controller.
    public var onStopHelper: ((String) -> Void)?
    /// Called when the user clicks a helper's bird: show it in the Milo window. Set by main.swift.
    public var onOpenHelper: ((String) -> Void)?

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
        case let .looking(on):
            looking = on
        case let .confirm(id, text):
            question = PendingQuestion(id: id, text: text)
            scheduleBubbleHide()
        case let .confirmDone(id, _):
            guard question?.id == id else { return }
            question = nil
            scheduleBubbleHide()
        case let .helpers(list):
            if list != helpers { helpers = list }
        case .dictation, .uiConfig, .history, .entry, .replyDelta, .activity, .lookRequest, .handsRequest,
             .handsSession, .flyTo, .appRequest, .handsBorrow, .facts, .unknown:
            break
        }
    }

    /// The user clicked Yes or No. The question goes away at once; `confirm_done` confirms it.
    public func answer(_ yes: Bool) {
        guard let question else { return }
        self.question = nil
        onAnswer?(question, yes)
        scheduleBubbleHide()
    }

    /// The user clicked Stop on the helper `id`.
    public func stopHelper(_ id: String) {
        onStopHelper?(id)
    }

    /// The user clicked a helper's bird or row.
    public func openHelper(_ id: String) {
        onOpenHelper?(id)
    }

    /// Shows text in the bubble for a while. Empty text hides it.
    public func show(_ text: String) {
        bubble = text.isEmpty ? nil : text
        scheduleBubbleHide()
    }

    private func scheduleBubbleHide() {
        hideBubble?.cancel()
        hideBubble = nil
        // A question stays up until it is answered or over.
        guard let text = bubble, state != .speaking, question == nil else { return }
        hideBubble = scheduler.after(Self.bubbleDuration(for: text)) { [weak self] in
            guard let self else { return }
            bubble = nil
            heard = nil
            if state == .idle { emotion = .neutral }
        }
    }
}
