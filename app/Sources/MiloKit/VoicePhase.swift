import Foundation

/// The talk or dictate key as the app saw it, a frame before the brain can answer. It lets the overlay react
/// the instant the key goes down instead of after the hold is confirmed and the brain's state comes back.
public enum Ear: Equatable, Sendable {
    /// The key is down. It may still turn out to be a tap or a shortcut, so only the small light shows.
    case armed(ListenMode)
    /// A real hold, or a double tap locked it on: Milo is listening.
    case open(ListenMode)
    /// The key came up after a real hold: the short "got it" beat before the words come back.
    case caught(ListenMode)

    public var mode: ListenMode {
        switch self {
        case let .armed(mode), let .open(mode), let .caught(mode): mode
        }
    }
}

/// What the small capsule over Milo shows about his ears and his head, one at a time. It changes shape from
/// one to the next, so the user sees the key go down, the voice come in, the release land and Milo think.
public enum VoicePhase: Equatable, Sendable {
    /// The key just went down: a small recording light.
    case armed(ListenMode)
    /// The level meter and the words so far. `handsFree`: a double tap locked it on.
    case listening(ListenMode, handsFree: Bool)
    /// "Got it", right after the key came up.
    case caught(ListenMode)
    /// The final pass over the recording.
    case transcribing(ListenMode)
    /// Dictation went into the focused app.
    case pasted
    /// Milo works on an answer that has no words yet.
    case thinking
    /// No brain to talk to (starting, or restarting).
    case offline

    /// Picks the phase from the model's state. Order matters: the user's own key beats what the brain last said,
    /// since the brain's answer is always a moment behind.
    public static func of(state: MiloState, ear: Ear?, handsFree: ListenMode?, pasted: Bool, connected: Bool,
                          lastMode: ListenMode, answering: Bool) -> VoicePhase? {
        guard connected else { return .offline }
        if case let .caught(mode) = ear {
            return pasted && mode == .dictate ? .pasted : .caught(mode)
        }
        switch state {
        case .listening: return .listening(.talk, handsFree: handsFree != nil)
        case .dictating: return .listening(.dictate, handsFree: handsFree != nil)
        default: break
        }
        switch ear {
        case let .open(mode): return .listening(mode, handsFree: handsFree != nil)
        case let .armed(mode): return .armed(mode)
        case .caught, nil: break
        }
        if pasted { return .pasted }
        switch state {
        case .transcribing: return .transcribing(lastMode)
        case .thinking where !answering: return .thinking
        default: return nil
        }
    }

    /// The mode whose colour the capsule wears; nil for neutral phases.
    public var mode: ListenMode? {
        switch self {
        case let .armed(mode), let .listening(mode, _), let .caught(mode), let .transcribing(mode): mode
        case .pasted: .dictate
        case .thinking: .talk
        case .offline: nil
        }
    }

    public var isArmed: Bool {
        if case .armed = self { true } else { false }
    }

    /// Recording, in any form: the answer bubble steps aside.
    public var recording: Bool {
        switch self {
        case .armed, .listening, .caught: true
        default: false
        }
    }

    /// A short name for VoiceOver.
    public var spoken: String {
        switch self {
        case .armed, .listening(.talk, _): "Milo is listening"
        case .listening(.dictate, _): "Milo is taking dictation"
        case .caught: "Milo got it"
        case .transcribing(.dictate): "Milo is writing it down"
        case .transcribing(.talk): "Milo is working out what you said"
        case .pasted: "Pasted"
        case .thinking: "Milo is thinking"
        case .offline: "Milo is waking up"
        }
    }
}
