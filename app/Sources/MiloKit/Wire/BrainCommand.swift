/// A message to the brain (`app_to_brain` in protocol/messages.json).
public enum BrainCommand: Equatable, Sendable {
    /// Start recording. `tentative`: record but show nothing until `listenConfirm` or `listenStop`,
    /// since the key press may still turn out to be a tap.
    case listenStart(ListenMode, tentative: Bool = false)
    /// Show a tentative recording: the hold is real, or a double tap locked it on.
    case listenConfirm
    case listenStop
    case listenCancel
    /// Typed chat. `speak` false: Milo answers in text only, without audio.
    case text(String, speak: Bool = true)
    /// The Milo window opened: send the recent conversation again.
    case getHistory
    /// Frontmost app name and seconds since the last keyboard or mouse input.
    case context(app: String, idleSeconds: Double)
    /// Mute or unmute proactive nudges.
    case mute(Bool)
    /// What was captured for look_request `id`.
    case lookResult(id: String, ScreenCapture)
    /// The "What's this?" shortcut: the selection, or the window if nothing was selected.
    case whatsThis(ScreenCapture)
    /// The outcome of hands_request `id`. `error` is plain words for the worker when `ok` is false.
    case handsResult(id: String, ok: Bool, result: [String: JSONValue], error: String = "")
    /// The user took over the mouse or keyboard ("user") or pressed esc ("escape").
    case handsStop(reason: String)
    /// The user clicked Yes or No on the question `id`.
    case confirmAnswer(id: String, yes: Bool)
    /// The answer to `app_request` `id`.
    case appResponse(id: String, outcome: AppOutcome)
    /// The "What Milo knows" window opened: send the facts.
    case getFacts
    /// The user clicked Forget on fact `id`.
    case forgetFact(id: String)
    /// The user changed fact `id` to `text`.
    case editFact(id: String, text: String)
}

/// What the app did with an `app_request`: a JSON result, or a plain-language error for the user.
public enum AppOutcome: Equatable, Sendable {
    case success(JSONValue)
    case failure(String)
}

extension BrainCommand: Encodable {
    private enum Key: String, CodingKey {
        case type, mode, text, app, on, tentative, speak, id, capture, ok, result, error, reason, yes
        case idleSeconds = "idle_s"
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: Key.self)
        switch self {
        case let .listenStart(mode, tentative):
            try c.encode("listen_start", forKey: .type)
            try c.encode(mode, forKey: .mode)
            if tentative { try c.encode(true, forKey: .tentative) }
        case .listenConfirm:
            try c.encode("listen_confirm", forKey: .type)
        case .listenStop:
            try c.encode("listen_stop", forKey: .type)
        case .listenCancel:
            try c.encode("listen_cancel", forKey: .type)
        case let .text(text, speak):
            try c.encode("text", forKey: .type)
            try c.encode(text, forKey: .text)
            if !speak { try c.encode(false, forKey: .speak) }
        case .getHistory:
            try c.encode("get_history", forKey: .type)
        case let .context(app, idleSeconds):
            try c.encode("context", forKey: .type)
            try c.encode(app, forKey: .app)
            try c.encode(idleSeconds, forKey: .idleSeconds)
        case let .mute(on):
            try c.encode("mute", forKey: .type)
            try c.encode(on, forKey: .on)
        case let .lookResult(id, capture):
            try c.encode("look_result", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(capture, forKey: .capture)
        case let .whatsThis(capture):
            try c.encode("whats_this", forKey: .type)
            try c.encode(capture, forKey: .capture)
        case let .handsResult(id, ok, result, error):
            try c.encode("hands_result", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(ok, forKey: .ok)
            try c.encode(result, forKey: .result)
            if !error.isEmpty { try c.encode(error, forKey: .error) }
        case let .handsStop(reason):
            try c.encode("hands_stop", forKey: .type)
            try c.encode(reason, forKey: .reason)
        case let .confirmAnswer(id, yes):
            try c.encode("confirm_answer", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(yes, forKey: .yes)
        case let .appResponse(id, outcome):
            try c.encode("app_response", forKey: .type)
            try c.encode(id, forKey: .id)
            switch outcome {
            case let .success(result):
                try c.encode(true, forKey: .ok)
                try c.encode(result, forKey: .result)
            case let .failure(message):
                try c.encode(false, forKey: .ok)
                try c.encode(message, forKey: .error)
            }
        case .getFacts:
            try c.encode("get_facts", forKey: .type)
        case let .forgetFact(id):
            try c.encode("forget_fact", forKey: .type)
            try c.encode(id, forKey: .id)
        case let .editFact(id, text):
            try c.encode("edit_fact", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(text, forKey: .text)
        }
    }
}
