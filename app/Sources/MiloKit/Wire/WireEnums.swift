/// What the brain is doing. Raw values are the wire strings (brain/src/milo/core/types.py).
public enum MiloState: String, CaseIterable, Sendable {
    case idle, listening, dictating, transcribing, thinking, speaking
}

/// The character's face. Raw values are the wire strings.
public enum Emotion: String, CaseIterable, Sendable {
    case neutral, happy, excited, thinking, concerned, sad, sleepy, confused
}

/// How Milo looks (`[ui] character`). Raw values are the wire strings.
public enum CharacterStyle: String, CaseIterable, Sendable {
    /// The small lavender bird.
    case pip
    /// The purple robot with the antenna.
    case classic
    /// A small round dragon with tiny wings, who puffs smoke while he thinks.
    case dragon
    /// A fox folded from warm paper, who turns into a paper plane to fly.
    case kit
    /// A small lantern firefly, who points with a beam of light.
    case glow
}

/// Why the user is holding a push-to-talk key.
public enum ListenMode: String, CaseIterable, Sendable, Encodable {
    /// Speech becomes text pasted into the focused app.
    case dictate
    /// Speech is a turn in the conversation with Milo.
    case talk
}
