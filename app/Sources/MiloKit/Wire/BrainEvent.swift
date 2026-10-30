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
    /// `whatsThisKey` is the "What's this?" shortcut, e.g. "ctrl+option+m"; "" turns it off, nil keeps it.
    /// `character` is nil when missing or unknown, which keeps the current look.
    case uiConfig(dictateKey: String, talkKey: String, handsFreeMaxSeconds: Double? = nil, whatsThisKey: String? = nil,
                  character: CharacterStyle? = nil)
    /// The recent conversation for the Milo window, oldest first.
    case history([TranscriptEntry])
    /// A transcript entry was added or changed; replaces the one with the same id.
    case entry(TranscriptEntry)
    /// More text of the streaming Milo reply `id`.
    case replyDelta(id: String, text: String)
    /// A step of the running task `taskID` started or ended; replaces the step with the same id.
    case activity(taskID: String, step: ActivityStep)
    /// Capture the frontmost window ("window") or the selection ("selection") and answer with look_result.
    case lookRequest(id: String, mode: String)
    /// Milo is looking at the screen: show the eye.
    case looking(Bool)
    /// Run one computer-use action and answer with hands_result.
    case handsRequest(id: String, tool: String, args: [String: JSONValue])
    /// The worker acts on screen: show the frame, stop on real user input.
    case handsSession(Bool)
    /// Where Milo is about to act; nil sends him home.
    case flyTo(ScreenPoint?)
    /// Milo asks a yes-or-no question before an action; shown with Yes and No until `confirmDone`.
    case confirm(id: String, question: String)
    /// The question `id` is over: "yes", "no" or "timeout".
    case confirmDone(id: String, answer: String)
    /// Work only the app may do (EventKit). Answered with `BrainCommand.appResponse` and the same id.
    case appRequest(id: String, op: String, args: JSONValue)
    /// The helpers working for Milo, oldest first; finished ones stay a few seconds.
    case helpers([HelperInfo])
    /// The user lent Milo one real device ("mouse" or "keyboard") for an action that can't be done in the
    /// background. The app hands it back on its own a while after the last such action, or when the session ends.
    case handsBorrow(on: Bool, what: String)
    /// The user's routines by name, and the recipe drafts waiting for a look.
    case routines([RoutineInfo], drafts: [RoutineDraft])
    case unknown(String)
}

extension BrainEvent: Decodable {
    private enum Key: String, CodingKey {
        case type, state, emotion, text, value, entries, entry, id, step, mode, on, tool, args, point, question, answer, op, what
        case taskID = "task_id"
        case whatsThisKey = "whats_this_key"
        case dictateKey = "dictate_key"
        case talkKey = "talk_key"
        case handsFreeMaxSeconds = "hands_free_max_s"
        case character
        case helpers
        case routines, drafts
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
                             whatsThisKey: try c.decodeIfPresent(String.self, forKey: .whatsThisKey),
                             character: try c.decodeIfPresent(String.self, forKey: .character)
                                .flatMap(CharacterStyle.init(rawValue:)))
        case "history": self = .history(try c.decode([TranscriptEntry].self, forKey: .entries))
        case "entry": self = .entry(try c.decode(TranscriptEntry.self, forKey: .entry))
        case "reply_delta": self = .replyDelta(id: try c.decode(String.self, forKey: .id), text: try text())
        case "activity":
            self = .activity(taskID: try c.decode(String.self, forKey: .taskID),
                             step: try c.decode(ActivityStep.self, forKey: .step))
        case "look_request":
            self = .lookRequest(id: try c.decode(String.self, forKey: .id),
                                mode: try c.decodeIfPresent(String.self, forKey: .mode) ?? "window")
        case "looking": self = .looking(try c.decode(Bool.self, forKey: .on))
        case "hands_request":
            self = .handsRequest(id: try c.decode(String.self, forKey: .id), tool: try c.decode(String.self, forKey: .tool),
                                 args: try c.decodeIfPresent([String: JSONValue].self, forKey: .args) ?? [:])
        case "hands_session": self = .handsSession(try c.decode(Bool.self, forKey: .on))
        case "fly_to": self = .flyTo(try c.decodeIfPresent(ScreenPoint.self, forKey: .point))
        case "confirm": self = .confirm(id: try c.decode(String.self, forKey: .id),
                                        question: try c.decode(String.self, forKey: .question))
        case "confirm_done": self = .confirmDone(id: try c.decode(String.self, forKey: .id),
                                                 answer: try c.decode(String.self, forKey: .answer))
        case "app_request":
            self = .appRequest(id: try c.decode(String.self, forKey: .id), op: try c.decode(String.self, forKey: .op),
                               args: try c.decodeIfPresent(JSONValue.self, forKey: .args) ?? .object([:]))
        case "helpers": self = .helpers(try c.decode([HelperInfo].self, forKey: .helpers))
        case "hands_borrow":
            self = .handsBorrow(on: try c.decode(Bool.self, forKey: .on),
                                what: try c.decodeIfPresent(String.self, forKey: .what) ?? "")
        case "routines":
            self = .routines(try c.decodeIfPresent([RoutineInfo].self, forKey: .routines) ?? [],
                             drafts: try c.decodeIfPresent([RoutineDraft].self, forKey: .drafts) ?? [])
        default: self = .unknown(type)
        }
    }
}
