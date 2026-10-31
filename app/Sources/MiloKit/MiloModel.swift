import Foundation
import Combine

/// A yes-or-no question Milo waits on before an action.
public struct PendingQuestion: Equatable, Sendable {
    public let id: String
    public let text: String
    /// Buttons of its own instead of Yes and No, like "Always for Zoom".
    public let choices: [ConfirmChoice]

    public init(id: String, text: String, choices: [ConfirmChoice] = []) {
        self.id = id
        self.text = text
        self.choices = choices
    }
}

/// Everything the character view draws. Updated on the main queue.
public final class MiloModel: ObservableObject {
    @Published public var state: MiloState = .idle
    @Published public var emotion: Emotion = .neutral
    @Published public var bubble: String?
    @Published public var heard: String?
    /// The mic or voice level, 0...1, about 20 times a second. Kept in `live`, which only the figure and the
    /// meter watch, so it doesn't redraw every view of this model each time.
    public var level: Double {
        get { live.level }
        set { if live.level != newValue { live.level = newValue } }
    }
    /// What changes many times a second while Milo listens or speaks.
    public let live = LiveLevel()
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
    /// Milo records a meeting: a red dot shows on him and in the menu bar. Set by the meeting controller.
    @Published public var recording = false
    /// The user lent Milo the real mouse and keyboard: the frame around the screen shows, and any touch stops him.
    @Published public var handsBorrowed = false
    /// The window Milo works in, in AppKit global coordinates: outlined, and Pip perches on its corner.
    @Published public var workingWindow: CGRect?
    /// How Milo looks, from the brain's `ui_config`.
    @Published public var character: CharacterStyle = .milo
    /// Milo by message, for the menu. nil while messages are off.
    @Published public var remote: RemoteStatus?
    /// A point on screen Milo should fly to and point at, in AppKit global screen coordinates (points,
    /// origin bottom-left of the main display). nil sends him home to his corner.
    @Published public var flyTarget: CGPoint?
    /// Where he is on the way, set by the overlay panel that moves him.
    @Published public internal(set) var flight: Flight = .perched
    /// Shown with Yes and No in the bubble and the Milo window until answered or over.
    @Published public private(set) var question: PendingQuestion?
    /// Called with the user's click on Yes (true) or No, and the choice if the question has its own. Set by the
    /// controller.
    public var onAnswer: ((PendingQuestion, Bool, String) -> Void)?
    /// Meeting notes: the capsule by Milo, the menu bar and the meeting's page follow it.
    public let meeting: MeetingModel
    /// The helpers working for Milo, oldest first, from the brain's `helpers` event.
    @Published public private(set) var helpers: [HelperInfo] = []
    /// Called when the user clicks Stop on a helper. Set by the controller.
    public var onStopHelper: ((String) -> Void)?
    /// Called when the user clicks a helper's bird: show it in the Milo window. Set by main.swift.
    public var onOpenHelper: ((String) -> Void)?
    /// The user's routines by name, from the brain's `routines` event.
    @Published public private(set) var routines: [RoutineInfo] = []
    /// Recipes Milo wrote down that wait for the user's look: Save, or "Change it".
    @Published public private(set) var drafts: [RoutineDraft] = []
    /// Called when the user clicks Run now, Pause, Resume or Delete on a routine. Set by the controller.
    public var onRoutine: ((String, RoutineAction) -> Void)?
    /// Called with a draft's id and true for Save, false for throwing it away. Set by the controller.
    public var onDraftAnswer: ((String, Bool) -> Void)?
    /// The talk or dictate key as the app saw it, ahead of the brain. Set by the controller.
    @Published public private(set) var ear: Ear?
    /// Dictation just went into the focused app: "Pasted" shows for a moment.
    @Published public private(set) var pasted = false
    /// How the bubble's words keep pace with Milo's voice.
    @Published public private(set) var reveal = SpeechReveal()
    /// A button under the bubble that helps with what it says, such as "Fix it" on a missing permission.
    @Published public private(set) var bubbleAction: BubbleAction?
    /// Called when the user clicks the bubble's button. Set by main.swift.
    public var onBubbleAction: ((BubbleAction) -> Void)?
    /// When Milo started thinking, on `now`'s clock; nil while he isn't.
    public private(set) var thinkingSince: TimeInterval?
    /// The mode of the newest recording, for the colour of what comes after it.
    public private(set) var lastMode: ListenMode = .talk
    /// Seconds on a monotonic clock, for pacing the bubble's words.
    public let now: () -> TimeInterval

    private let scheduler: Scheduler
    private var hideBubble: ScheduledTask?
    private var endBeat: ScheduledTask?
    private var endPasted: ScheduledTask?

    public init(scheduler: Scheduler, clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }) {
        self.scheduler = scheduler
        now = clock
        meeting = MeetingModel(clock: clock)
    }

    /// How long "Got it" stays after the key comes up. Long enough to read, short enough not to hold anything up.
    public static let caughtBeat: TimeInterval = 0.6
    /// How long "Pasted" stays.
    public static let pastedBeat: TimeInterval = 1.4

    /// What the capsule over Milo shows now.
    public var voicePhase: VoicePhase? {
        VoicePhase.of(state: state, ear: ear, handsFree: handsFree, pasted: pasted, connected: connected,
                      lastMode: lastMode, answering: bubble != nil || question != nil)
    }

    /// How long a bubble stays up: longer for longer text, at most 20 s.
    public static func bubbleDuration(for text: String) -> TimeInterval {
        min(20, 4 + Double(text.count) / 15)
    }

    /// Applies a display event. Dictation, ui_config, settings and unknown events are not the model's business.
    public func apply(_ event: BrainEvent) {
        switch event {
        case let .state(new):
            let wasSpeaking = state == .speaking
            state = new
            if new == .listening { lastMode = .talk }
            if new == .dictating { lastMode = .dictate }
            if wasSpeaking && new != .speaking { reveal.finish() }
            if new != .thinking { thinkingSince = nil } else if thinkingSince == nil { thinkingSince = now() }
            if state == .listening || state == .dictating { heard = nil }
            // A new question replaces the last answer, so that answer's hide timer can't later
            // wipe the new `heard` while Milo thinks.
            if state == .listening { clearBubble() }
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
        case let .confirm(id, text, choices):
            question = PendingQuestion(id: id, text: text, choices: choices)
            scheduleBubbleHide()
        case let .confirmDone(id, _):
            guard question?.id == id else { return }
            question = nil
            scheduleBubbleHide()
        case let .helpers(list):
            if list != helpers { helpers = list }
        case let .routines(list, waiting):
            if list != routines { routines = list }
            if waiting != drafts { drafts = waiting }
        case let .remote(status):
            remote = status
        case let .meetingStatus(status):
            let before = meeting.status
            meeting.apply(event)
            meetingChanged(from: before, to: status)
        case .meetingLines, .meetingNotes:
            meeting.apply(event)
        case .dictation, .uiConfig, .history, .entry, .replyDelta, .activity, .lookRequest, .handsRequest,
             .handsSession, .flyTo, .appRequest, .handsBorrow, .facts, .settings, .usage, .meetingRecord,
             .conversations, .conversation, .searchResults, .reminders, .unknown:
            break
        }
    }

    /// The user clicked Yes or No. The question goes away at once; `confirm_done` confirms it.
    public func answer(_ yes: Bool) {
        guard let question else { return }
        self.question = nil
        onAnswer?(question, yes, "")
        scheduleBubbleHide()
    }

    /// The user clicked one of the question's own buttons.
    public func answer(_ choice: ConfirmChoice) {
        guard let question else { return }
        self.question = nil
        onAnswer?(question, choice.yes, choice.id)
        scheduleBubbleHide()
    }

    /// What Milo says by himself when meeting notes start, can't hear something, or are ready: each with the button
    /// that helps next.
    private func meetingChanged(from before: MeetingStatus, to now: MeetingStatus) {
        let same = before.id == now.id
        if now.phase == .recording && !(same && before.live) {
            show(bubble ?? "Taking notes.", action: .copyConsent)
        }
        if now.live && !now.error.isEmpty && !(same && before.error == now.error) {
            show(now.error, action: now.fix == .microphone ? .microphone : .callAudio)
        }
        if now.phase == .done && !(same && before.phase == .done) {
            show(now.step.isEmpty ? "Your notes from “\(now.title)” are ready." : now.step,
                 action: .openMeeting(now.id))
        }
    }

    /// The user clicked Stop on the helper `id`.
    public func stopHelper(_ id: String) {
        onStopHelper?(id)
    }

    /// The user clicked a button on the routine `id`.
    public func routine(_ id: String, _ action: RoutineAction) {
        onRoutine?(id, action)
    }

    /// The user saved a draft (true) or threw it away (false). It goes at once; the brain confirms it.
    public func answerDraft(_ id: String, save: Bool) {
        drafts.removeAll { $0.id == id }
        onDraftAnswer?(id, save)
    }

    /// The user clicked a helper's bird or row.
    public func openHelper(_ id: String) {
        onOpenHelper?(id)
    }

    /// Shows text in the bubble for a while, with a button that helps if there is one. Empty text hides it.
    public func show(_ text: String, action: BubbleAction? = nil) {
        guard !text.isEmpty else {
            clearBubble()
            return scheduleBubbleHide()
        }
        reveal.show(text, speaking: state == .speaking && action == nil, at: now())
        bubble = text
        if bubbleAction != action { bubbleAction = action }
        scheduleBubbleHide()
    }

    /// The user clicked the bubble's button.
    public func performBubbleAction() {
        guard let bubbleAction else { return }
        if bubbleAction == .copyConsent {
            // Done here, so the bubble can say it worked.
            meeting.copyConsent()
            return show(Self.copiedConsent)
        }
        onBubbleAction?(bubbleAction)
    }

    /// What the bubble says once the note for the call's chat is on the clipboard.
    public static let copiedConsent = "Copied. Paste it into the call's chat."

    // MARK: The keys, a frame ahead of the brain

    /// The talk or dictate key went down: the recording light shows at once.
    public func press(_ mode: ListenMode) {
        endBeat?.cancel()
        lastMode = mode
        set(ear: .armed(mode))
    }

    /// The hold is real, or a double tap locked it on: Milo listens.
    public func hold(_ mode: ListenMode) {
        lastMode = mode
        set(ear: .open(mode))
    }

    /// The key came up after a hold: "Got it" for a beat, then whatever the brain says.
    public func release(_ mode: ListenMode) {
        set(ear: .caught(mode))
        endBeat?.cancel()
        endBeat = scheduler.after(Self.caughtBeat) { [weak self] in
            guard let self, case .caught = self.ear else { return }
            set(ear: nil)
        }
    }

    /// A tap, a shortcut or esc: the light goes out.
    public func cancelPress() {
        endBeat?.cancel()
        set(ear: nil)
    }

    /// Dictation went into the focused app.
    public func pasted(_ text: String) {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        if !pasted { pasted = true }
        endPasted?.cancel()
        endPasted = scheduler.after(Self.pastedBeat) { [weak self] in self?.pasted = false }
    }

    private func clearBubble() {
        bubble = nil
        bubbleAction = nil
        reveal.clear()
    }

    private func set(ear new: Ear?) {
        if ear != new { ear = new }
    }

    private func scheduleBubbleHide() {
        hideBubble?.cancel()
        hideBubble = nil
        // A question stays up until it is answered or over.
        guard let text = bubble, state != .speaking, question == nil else { return }
        hideBubble = scheduler.after(Self.bubbleDuration(for: text)) { [weak self] in
            guard let self else { return }
            clearBubble()
            heard = nil
            if state == .idle { emotion = .neutral }
        }
    }
}

/// The level on its own, for the few views that follow it.
public final class LiveLevel: ObservableObject {
    @Published public internal(set) var level: Double = 0
}

/// What the button under a bubble does.
public enum BubbleAction: Equatable, Sendable {
    /// Opens the permissions window, where each missing switch has its own button.
    case permissions
    /// Opens System Settings at the microphone's switches.
    case microphone
    /// Opens System Settings where Milo may hear the others in a call (System Audio Recording).
    case callAudio
    /// Puts the line for the call's chat on the clipboard.
    case copyConsent
    /// Shows a meeting's notes in the Milo window.
    case openMeeting(String)

    public var title: String {
        switch self {
        case .permissions, .microphone, .callAudio: "Fix it"
        case .copyConsent: "Copy a note for the chat"
        case .openMeeting: "Open notes"
        }
    }

    /// What the button does, for VoiceOver.
    public var hint: String {
        switch self {
        case .permissions: "Opens Milo's permissions window"
        case .microphone: "Opens the microphone settings in System Settings"
        case .callAudio: "Opens the screen and system audio recording settings in System Settings"
        case .copyConsent: "Copies a line telling the others that Milo takes notes, to paste into the call's chat"
        case .openMeeting: "Shows the meeting's notes in the Milo window"
        }
    }
}
