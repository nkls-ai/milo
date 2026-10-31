/// What the brain is doing. Raw values are the wire strings (brain/src/milo/core/types.py).
public enum MiloState: String, CaseIterable, Sendable {
    case idle, listening, dictating, transcribing, thinking, speaking
}

/// The character's face. Raw values are the wire strings.
public enum Emotion: String, CaseIterable, Sendable {
    case neutral, happy, excited, thinking, concerned, sad, sleepy, confused
}

/// Why the user is holding a push-to-talk key.
public enum ListenMode: String, CaseIterable, Sendable, Encodable {
    /// Speech becomes text pasted into the focused app.
    case dictate
    /// Speech is a turn in the conversation with Milo.
    case talk
}

/// What dictation does while the user speaks (`[dictation] stream`). Raw values are the wire strings.
public enum DictationStyle: String, CaseIterable, Sendable, Encodable {
    /// Nothing until the key is let go, then one pass over the whole recording.
    case off
    /// The words show next to Milo while the user speaks; the text is pasted on release.
    case preview
    /// Each phrase is typed into the app at the pause after it.
    case type
}
