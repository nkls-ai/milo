import Foundation

/// A dictation goes on from whatever is before the caret. Right after a word or a full stop it needs a space:
/// "…was pattern" then "And why…" pasted "patternAnd" (2026-10-31). After a space, an opening bracket or quote, or
/// at the start of a field it doesn't, and neither does text that starts with punctuation or a space of its own
/// (the brain starts every later phrase of a recording with one).
public enum DictationSpacing {
    static let opening: Set<Character> = ["(", "[", "{", "“", "‘", "„", "‚", "«", "/"]

    public static func spaced(_ text: String, after before: Character?) -> String {
        guard let before, let first = text.first, !before.isWhitespace, !opening.contains(before),
              !first.isWhitespace, !first.isPunctuation else { return text }
        return " " + text
    }
}
