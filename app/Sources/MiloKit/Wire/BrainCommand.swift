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
    /// The user clicked Yes or No on the question `id`.
    case confirmAnswer(id: String, yes: Bool)
    /// The answer to `app_request` `id`.
    case appResponse(id: String, outcome: AppOutcome)
}

/// What the app did with an `app_request`: a JSON result, or a plain-language error for the user.
public enum AppOutcome: Equatable, Sendable {
    case success(JSONValue)
    case failure(String)
}

extension BrainCommand: Encodable {
    private enum Key: String, CodingKey {
        case type, mode, text, app, on, tentative, speak, id, yes, ok, result, error
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
        }
    }
}
