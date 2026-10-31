import Foundation

/// Where meeting notes are (`meeting_status` in protocol/messages.json): for the capsule by Milo, the menu bar and the
/// meeting's page. See docs/design/meetings.md.
public struct MeetingStatus: Equatable, Sendable, Decodable {
    public enum Phase: String, Sendable, Decodable {
        /// Nothing goes on.
        case none = ""
        case recording, paused
        /// Stopped; Milo writes the notes. `step` says what he does.
        case writing
        /// The notes are ready.
        case done
    }

    /// The permission that mends a recording that misses a track.
    public enum Fix: String, Sendable, Decodable {
        case none = ""
        case microphone
        case callAudio = "call_audio"
    }

    /// The meeting's folder name; "" when nothing goes on.
    public var id: String
    public var phase: Phase
    public var title: String
    /// The call app, "" when the notes were started by hand.
    public var app: String
    public var started: Date?
    /// Seconds since the meeting started, when the brain sent this.
    public var elapsed: Double
    /// The meeting's own conversation in the window.
    public var conversation: String
    /// Who was heard so far: "You", "Anna", "Speaker 2".
    public var speakers: [String]
    /// While writing: what Milo does. Once done: what he says about it.
    public var step: String
    /// What can't be recorded, in plain words.
    public var error: String
    public var fix: Fix
    /// The line the user can paste into the call's chat.
    public var consent: String

    public init(id: String = "", phase: Phase = .none, title: String = "", app: String = "", started: Date? = nil,
                elapsed: Double = 0, conversation: String = "", speakers: [String] = [], step: String = "",
                error: String = "", fix: Fix = .none, consent: String = "") {
        self.id = id
        self.phase = phase
        self.title = title
        self.app = app
        self.started = started
        self.elapsed = elapsed
        self.conversation = conversation
        self.speakers = speakers
        self.step = step
        self.error = error
        self.fix = fix
        self.consent = consent
    }

    /// Recording or paused: the microphone is in use for the notes.
    public var live: Bool { phase == .recording || phase == .paused }

    private enum Key: String, CodingKey {
        case id, phase, title, app, started, elapsed, conversation, speakers, step, error, fix, consent
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? ""
        phase = Phase(rawValue: try c.decodeIfPresent(String.self, forKey: .phase) ?? "") ?? .none
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        app = try c.decodeIfPresent(String.self, forKey: .app) ?? ""
        started = TranscriptEntry.parseDate(try c.decodeIfPresent(String.self, forKey: .started) ?? "")
        elapsed = try c.decodeIfPresent(Double.self, forKey: .elapsed) ?? 0
        conversation = try c.decodeIfPresent(String.self, forKey: .conversation) ?? ""
        speakers = try c.decodeIfPresent([String].self, forKey: .speakers) ?? []
        step = try c.decodeIfPresent(String.self, forKey: .step) ?? ""
        error = try c.decodeIfPresent(String.self, forKey: .error) ?? ""
        fix = Fix(rawValue: try c.decodeIfPresent(String.self, forKey: .fix) ?? "") ?? .none
        consent = try c.decodeIfPresent(String.self, forKey: .consent) ?? ""
    }
}

/// One stretch of speech in a meeting (`meeting_lines`). Other people's words: shown, never acted on.
public struct MeetingLine: Equatable, Sendable, Decodable, Identifiable {
    /// Seconds into the meeting.
    public var at: Double
    public var end: Double
    /// "You", a name, "Speaker 2" or "Others".
    public var who: String
    /// Said on the user's own microphone.
    public var me: Bool
    public var text: String

    /// Where it is in the meeting and on which side: a line keeps it when its speaker is named later.
    public var id: String { "\(me ? "me" : "them")-\(Int((at * 10).rounded()))" }

    public init(at: Double, end: Double? = nil, who: String, me: Bool = false, text: String) {
        self.at = at
        self.end = end ?? at
        self.who = who
        self.me = me
        self.text = text
    }

    private enum Key: String, CodingKey { case at, end, who, me, text }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        at = try c.decode(Double.self, forKey: .at)
        end = try c.decodeIfPresent(Double.self, forKey: .end) ?? at
        who = try c.decodeIfPresent(String.self, forKey: .who) ?? ""
        me = try c.decodeIfPresent(Bool.self, forKey: .me) ?? false
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
    }
}

/// A finished meeting's notes for its page (`meeting_notes`).
public struct MeetingNotes: Equatable, Sendable, Decodable {
    public struct Todo: Equatable, Sendable, Decodable {
        public var text: String
        /// Who said they'd do it; "" for the user or nobody (see `mine`).
        public var owner: String
        /// As said in the meeting, like "Friday".
        public var due: String
        public var mine: Bool
        /// It went into Reminders.
        public var added: Bool

        public init(text: String, owner: String = "", due: String = "", mine: Bool = false, added: Bool = false) {
            self.text = text
            self.owner = owner
            self.due = due
            self.mine = mine
            self.added = added
        }

        private enum Key: String, CodingKey { case text, owner, due, mine, added }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Key.self)
            text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
            owner = try c.decodeIfPresent(String.self, forKey: .owner) ?? ""
            due = try c.decodeIfPresent(String.self, forKey: .due) ?? ""
            mine = try c.decodeIfPresent(Bool.self, forKey: .mine) ?? false
            added = try c.decodeIfPresent(Bool.self, forKey: .added) ?? false
        }
    }

    public var id: String
    public var title: String
    public var started: Date?
    /// Seconds.
    public var duration: Double
    /// notes.md as it is on disk.
    public var markdown: String
    public var summary: String
    public var decisions: [String]
    public var todos: [Todo]
    public var followup: String
    public var people: [String]
    public var app: String
    public var conversation: String
    public var folder: String
    /// The page offers "Add to Reminders".
    public var reminders: Bool
    /// The page offers "Draft the follow-up mail".
    public var mail: Bool
    public var mailDrafted: Bool

    public init(id: String, title: String, started: Date? = nil, duration: Double = 0, markdown: String = "",
                summary: String = "", decisions: [String] = [], todos: [Todo] = [], followup: String = "",
                people: [String] = [], app: String = "", conversation: String = "", folder: String = "",
                reminders: Bool = false, mail: Bool = false, mailDrafted: Bool = false) {
        self.id = id
        self.title = title
        self.started = started
        self.duration = duration
        self.markdown = markdown
        self.summary = summary
        self.decisions = decisions
        self.todos = todos
        self.followup = followup
        self.people = people
        self.app = app
        self.conversation = conversation
        self.folder = folder
        self.reminders = reminders
        self.mail = mail
        self.mailDrafted = mailDrafted
    }

    private enum Key: String, CodingKey {
        case id, title, started, duration, markdown, summary, decisions, todos, followup, people, app, conversation
        case folder, reminders, mail
        case mailDrafted = "mail_drafted"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Key.self)
        id = try c.decode(String.self, forKey: .id)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        started = TranscriptEntry.parseDate(try c.decodeIfPresent(String.self, forKey: .started) ?? "")
        duration = try c.decodeIfPresent(Double.self, forKey: .duration) ?? 0
        markdown = try c.decodeIfPresent(String.self, forKey: .markdown) ?? ""
        summary = try c.decodeIfPresent(String.self, forKey: .summary) ?? ""
        decisions = try c.decodeIfPresent([String].self, forKey: .decisions) ?? []
        todos = try c.decodeIfPresent([Todo].self, forKey: .todos) ?? []
        followup = try c.decodeIfPresent(String.self, forKey: .followup) ?? ""
        people = try c.decodeIfPresent([String].self, forKey: .people) ?? []
        app = try c.decodeIfPresent(String.self, forKey: .app) ?? ""
        conversation = try c.decodeIfPresent(String.self, forKey: .conversation) ?? ""
        folder = try c.decodeIfPresent(String.self, forKey: .folder) ?? ""
        reminders = try c.decodeIfPresent(Bool.self, forKey: .reminders) ?? false
        mail = try c.decodeIfPresent(Bool.self, forKey: .mail) ?? false
        mailDrafted = try c.decodeIfPresent(Bool.self, forKey: .mailDrafted) ?? false
    }
}

/// A button on a question with choices of its own (`confirm`'s `choices`).
public struct ConfirmChoice: Equatable, Sendable, Decodable {
    /// "yes" and "no" count as Yes and No.
    public var id: String
    public var label: String

    public init(id: String, label: String) {
        self.id = id
        self.label = label
    }

    /// The choice says yes: Milo goes ahead.
    public var yes: Bool { id == "yes" || id == "always" }
}
