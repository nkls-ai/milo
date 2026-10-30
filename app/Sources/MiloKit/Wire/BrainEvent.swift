/// A message from the brain (`brain_to_app` in protocol/messages.json).
///
/// An unknown `type` decodes to `.unknown(type)` so a newer brain doesn't break an older app.
/// An unknown state or emotion value falls back to `.idle` / `.neutral`.
public enum BrainEvent: Equatable, Sendable {
    case state(MiloState)
    case emotion(Emotion)
    /// Replace the speech bubble text.
    case bubble(String)
    /// What the user said, shown small above Milo's answer.
    case heard(String)
    /// Mic or voice loudness, 0...1.
    case level(Double)
    /// Final dictated text to insert into the focused app.
    case dictation(String)
    /// A short notice for the user, shown in the bubble.
    case status(String)
    /// The words heard so far in the recording in progress. Empty clears it.
    case partial(String)
    /// Push-to-talk key names: "fn", "right_option", "right_command", "right_control".
    /// `handsFreeMaxSeconds` caps a recording locked on by a double tap; nil keeps the app's default.
    /// `character` is nil when missing or unknown, which keeps the current look.
    case uiConfig(dictateKey: String, talkKey: String, handsFreeMaxSeconds: Double? = nil,
                  character: CharacterStyle? = nil)
    /// The recent conversation for the Milo window, oldest first.
    case history([TranscriptEntry])
    /// A transcript entry was added or changed; replaces the one with the same id.
    case entry(TranscriptEntry)
    /// More text of the streaming Milo reply `id`.
    case replyDelta(id: String, text: String)
    /// A step of the running task `taskID` started or ended; replaces the step with the same id.
    case activity(taskID: String, step: ActivityStep)
    case unknown(String)
}

extension BrainEvent: Decodable {
    private enum Key: String, CodingKey {
        case type, state, emotion, text, value, entries, entry, id, step
        case taskID = "task_id"
        case dictateKey = "dictate_key"
        case talkKey = "talk_key"
        case handsFreeMaxSeconds = "hands_free_max_s"
        case character
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        let type = try c.decode(String.self, forKey: .type)
        func text() throws -> String { try c.decode(String.self, forKey: .text) }
        switch type {
        case "state": self = .state(MiloState(rawValue: try c.decode(String.self, forKey: .state)) ?? .idle)
        case "emotion": self = .emotion(Emotion(rawValue: try c.decode(String.self, forKey: .emotion)) ?? .neutral)
        case "bubble": self = .bubble(try text())
        case "heard": self = .heard(try text())
        case "level": self = .level(try c.decode(Double.self, forKey: .value))
        case "dictation": self = .dictation(try text())
        case "status": self = .status(try text())
        case "partial": self = .partial(try text())
        case "ui_config":
            self = .uiConfig(dictateKey: try c.decode(String.self, forKey: .dictateKey),
                             talkKey: try c.decode(String.self, forKey: .talkKey),
                             handsFreeMaxSeconds: try c.decodeIfPresent(Double.self, forKey: .handsFreeMaxSeconds),
                             character: try c.decodeIfPresent(String.self, forKey: .character)
                                .flatMap(CharacterStyle.init(rawValue:)))
        case "history": self = .history(try c.decode([TranscriptEntry].self, forKey: .entries))
        case "entry": self = .entry(try c.decode(TranscriptEntry.self, forKey: .entry))
        case "reply_delta": self = .replyDelta(id: try c.decode(String.self, forKey: .id), text: try text())
        case "activity":
            self = .activity(taskID: try c.decode(String.self, forKey: .taskID),
                             step: try c.decode(ActivityStep.self, forKey: .step))
        default: self = .unknown(type)
        }
    }
}
