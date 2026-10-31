/// A message to the brain (`app_to_brain` in protocol/messages.json).
public enum BrainCommand: Equatable, Sendable {
    /// Start recording. `tentative`: record but show nothing until `listenConfirm` or `listenStop`,
    /// since the key press may still turn out to be a tap.
    case listenStart(ListenMode, tentative: Bool = false)
    /// Show a tentative recording: the hold is real, or a double tap locked it on.
    case listenConfirm
    case listenStop
    case listenCancel
    /// Typed chat. `speak` false: Milo answers in text only, without audio. `conversation`: typed into this
    /// earlier conversation, which picks it up again; "" goes on with the current one.
    case text(String, speak: Bool = true, conversation: String = "")
    /// The Milo window opened: send the recent conversation again.
    case getHistory
    /// The window's list of conversations: the latest page, or the one older than `before` (brain local time).
    case getConversations(before: String = "")
    /// The user opened a conversation: send it whole.
    case openConversation(id: String)
    case searchConversations(query: String)
    case renameConversation(id: String, title: String)
    /// ⌘N: the next turn starts a new conversation.
    case newConversation
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
    /// The user clicked Yes or No on the question `id`, or Allow always (`always`, with yes) where it was offered.
    case confirmAnswer(id: String, yes: Bool, always: Bool = false)
    /// The answer to `app_request` `id`.
    case appResponse(id: String, outcome: AppOutcome)
    /// The user clicked Stop on the helper `id`.
    case stopHelper(id: String)
    /// The user pressed the Stop button by Milo: stop talking, thinking, asking, every helper and the screen work.
    case stopAll
    /// The "What Milo knows" window opened: send the facts.
    case getFacts
    /// The user clicked Forget on fact `id`.
    case forgetFact(id: String)
    /// The user changed fact `id` to `text`.
    case editFact(id: String, text: String)
    /// A button in the Routines section: run, pause, resume or delete the routine `id`.
    case routine(id: String, action: RoutineAction)
    /// Save on the recipe draft `id` (true), or throw it away (false).
    case routineDraftAnswer(id: String, save: Bool)
    /// The Settings window opened: send the settings.
    case getSettings
    /// The Usage page opened or changed its range: send `usage` for the last `span` days (1 to 366).
    case getUsage(span: Int)
    /// Change one setting, e.g. section "ui", key "voice", value false.
    case setSetting(section: String, key: String, value: JSONValue)
    /// The menu's "Pause messages from your phone".
    case remotePause(Bool)
    /// The menu's "Disconnect phone": a new connection needs a new code shown on the Mac.
    case remoteForget
    /// A call app started using the microphone. `title` is its window or tab title, "" if unknown.
    case callStarted(app: String, bundle: String, title: String)
    /// That call app let go of the microphone.
    case callEnded(app: String)
    /// A finished 30 s chunk of meeting `id`: `track` "me" (the mic) or "them" (the call), `index` from 1,
    /// `start` its offset in the meeting. The last one may be shorter.
    case meetingChunk(MeetingChunk)
    /// What the app records: on connect, on a change of tracks, and once it stopped. `id` "" when nothing.
    /// `error` is plain words for the user when a track can't be recorded.
    case meetingRecording(id: String, on: Bool, tracks: [String], error: String = "")
    /// The user chose "Take meeting notes" or "Stop taking notes" in the menu.
    case meetingToggle(Bool)
    /// The user fixed words Milo had pasted. Only these pairs leave the app, never the field's text (ADR 21).
    case dictationFixed([DictationFix])
}

public struct MeetingChunk: Equatable, Sendable {
    public var id: String
    public var track: String
    public var index: Int
    public var path: String
    public var start: Double
    public var seconds: Double

    public init(id: String, track: String, index: Int, path: String, start: Double, seconds: Double) {
        self.id = id
        self.track = track
        self.index = index
        self.path = path
        self.start = start
        self.seconds = seconds
    }
}

/// What the app did with an `app_request`: a JSON result, or a plain-language error for the user.
public enum AppOutcome: Equatable, Sendable {
    case success(JSONValue)
    case failure(String)
}

extension BrainCommand: Encodable {
    private enum Key: String, CodingKey {
        case type, mode, text, app, on, tentative, speak, id, capture, ok, result, error, reason, yes, action, save
        case always
        case section, key, value
        case bundle, title, track, index, path, start, seconds, tracks
        case conversation, before, query, span, fixes, heard, meant
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
        case let .text(text, speak, conversation):
            try c.encode("text", forKey: .type)
            try c.encode(text, forKey: .text)
            if !speak { try c.encode(false, forKey: .speak) }
            if !conversation.isEmpty { try c.encode(conversation, forKey: .conversation) }
        case let .getConversations(before):
            try c.encode("get_conversations", forKey: .type)
            if !before.isEmpty { try c.encode(before, forKey: .before) }
        case let .openConversation(id):
            try c.encode("open_conversation", forKey: .type)
            try c.encode(id, forKey: .id)
        case let .searchConversations(query):
            try c.encode("search_conversations", forKey: .type)
            try c.encode(query, forKey: .query)
        case let .renameConversation(id, title):
            try c.encode("rename_conversation", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(title, forKey: .title)
        case .newConversation:
            try c.encode("new_conversation", forKey: .type)
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
        case let .confirmAnswer(id, yes, always):
            try c.encode("confirm_answer", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(yes, forKey: .yes)
            if always { try c.encode(true, forKey: .always) }
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
        case let .stopHelper(id):
            try c.encode("stop_helper", forKey: .type)
            try c.encode(id, forKey: .id)
        case .stopAll:
            try c.encode("stop_all", forKey: .type)
        case .getFacts:
            try c.encode("get_facts", forKey: .type)
        case let .forgetFact(id):
            try c.encode("forget_fact", forKey: .type)
            try c.encode(id, forKey: .id)
        case let .editFact(id, text):
            try c.encode("edit_fact", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(text, forKey: .text)
        case let .routine(id, action):
            try c.encode("routine", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(action, forKey: .action)
        case let .routineDraftAnswer(id, save):
            try c.encode("routine_draft_answer", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(save, forKey: .save)
        case .getSettings:
            try c.encode("get_settings", forKey: .type)
        case let .getUsage(span):
            try c.encode("get_usage", forKey: .type)
            try c.encode(span, forKey: .span)
        case let .setSetting(section, key, value):
            try c.encode("set_setting", forKey: .type)
            try c.encode(section, forKey: .section)
            try c.encode(key, forKey: .key)
            try c.encode(value, forKey: .value)
        case let .remotePause(on):
            try c.encode("remote_pause", forKey: .type)
            try c.encode(on, forKey: .on)
        case .remoteForget:
            try c.encode("remote_forget", forKey: .type)
        case let .callStarted(app, bundle, title):
            try c.encode("call_started", forKey: .type)
            try c.encode(app, forKey: .app)
            try c.encode(bundle, forKey: .bundle)
            try c.encode(title, forKey: .title)
        case let .callEnded(app):
            try c.encode("call_ended", forKey: .type)
            try c.encode(app, forKey: .app)
        case let .meetingChunk(chunk):
            try c.encode("meeting_chunk", forKey: .type)
            try c.encode(chunk.id, forKey: .id)
            try c.encode(chunk.track, forKey: .track)
            try c.encode(chunk.index, forKey: .index)
            try c.encode(chunk.path, forKey: .path)
            try c.encode(chunk.start, forKey: .start)
            try c.encode(chunk.seconds, forKey: .seconds)
        case let .meetingRecording(id, on, tracks, error):
            try c.encode("meeting_recording", forKey: .type)
            try c.encode(id, forKey: .id)
            try c.encode(on, forKey: .on)
            try c.encode(tracks, forKey: .tracks)
            if !error.isEmpty { try c.encode(error, forKey: .error) }
        case let .meetingToggle(on):
            try c.encode("meeting_toggle", forKey: .type)
            try c.encode(on, forKey: .on)
        case let .dictationFixed(fixes):
            try c.encode("dictation_fixed", forKey: .type)
            var list = c.nestedUnkeyedContainer(forKey: .fixes)
            for fix in fixes {
                var item = list.nestedContainer(keyedBy: Key.self)
                try item.encode(fix.heard, forKey: .heard)
                try item.encode(fix.meant, forKey: .meant)
            }
        }
    }
}
