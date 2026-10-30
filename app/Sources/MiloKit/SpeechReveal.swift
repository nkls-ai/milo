import Foundation

/// Paces the words of Milo's bubble to his voice. The brain sends the bubble text one spoken piece (about a
/// sentence) at a time, as the audio of that piece starts. The new piece is laid out at once, hidden, so nothing
/// reflows; its words then show one by one at the speed he speaks. When the next piece arrives, the last one
/// has been heard: whatever is still hidden shows, and the time it took teaches the speed for the next one.
///
/// Text that isn't spoken (a status, an answer while muted) shows whole.
public struct SpeechReveal: Equatable, Sendable {
    /// Characters per second before Milo has said anything: about 150 words a minute.
    public static let startRate = 15.0
    /// Speeds outside this are a pause or a hiccup, not his talking speed.
    static let rates = 9.0...30.0
    /// How long a new word takes to fade in.
    public static let fade = 0.16

    public private(set) var text = ""
    /// Characters shown in full when the newest piece arrived.
    public private(set) var settled = 0
    /// When the newest piece arrived, on the model's clock.
    public private(set) var since: TimeInterval = 0
    public private(set) var rate = startRate
    /// Whether the newest piece shows word by word.
    public private(set) var paced = false

    public init() {}

    /// The bubble changed to `new`. `speaking`: Milo says it now.
    public mutating func show(_ new: String, speaking: Bool, at now: TimeInterval) {
        defer { text = new }
        guard speaking, !new.isEmpty else {
            settled = new.count
            paced = false
            return
        }
        guard new != text else { return }
        if new.count > text.count, new.hasPrefix(text) {
            // The next piece: the last one has been heard.
            if paced { learn(Double(text.count - settled), in: now - since) }
            settled = text.count
        } else {
            settled = 0  // a new answer
        }
        since = now
        paced = true
    }

    /// The bubble went away. The speed he talks at stays.
    public mutating func clear() {
        text = ""
        settled = 0
        paced = false
    }

    private mutating func learn(_ characters: Double, in seconds: TimeInterval) {
        guard seconds > 0.3, characters > 8 else { return }
        let measured = min(Self.rates.upperBound, max(Self.rates.lowerBound, characters / seconds))
        rate = (rate + measured) / 2
    }

    /// Milo stopped talking: everything shows.
    public mutating func finish() {
        settled = text.count
        paced = false
    }

    /// What to draw at `now`: the characters shown in full, then one word fading in at `alpha`, then the hidden
    /// rest. Cuts fall on word ends, so a word never shows half.
    public func cut(at now: TimeInterval) -> (shown: Int, fresh: Int, alpha: Double) {
        guard paced, settled < text.count else { return (text.count, 0, 1) }
        let reach = settled + max(0, Int(((now - since) * rate).rounded(.down)))
        let chars = Array(text)
        let end = Self.wordEnd(in: chars, from: min(reach, chars.count))
        guard end > settled else { return (settled, 0, 1) }
        let start = Self.wordStart(in: chars, before: end, floor: settled)
        let revealedAt = since + Double(start - settled) / rate
        let alpha = min(1, max(0.2, (now - revealedAt) / Self.fade))
        return alpha >= 1 ? (end, 0, 1) : (start, end - start, alpha)
    }

    /// Whether every word shows at `now`.
    public func done(at now: TimeInterval) -> Bool {
        let cut = cut(at: now)
        return cut.shown + cut.fresh >= text.count && cut.alpha >= 1
    }

    /// The end of the word at `index`: the next space or the end. At a space, that space.
    static func wordEnd(in chars: [Character], from index: Int) -> Int {
        var i = index
        while i < chars.count, !chars[i].isWhitespace { i += 1 }
        return i
    }

    /// Where the word ending at `end` starts, not before `floor`, keeping the space in front of it.
    static func wordStart(in chars: [Character], before end: Int, floor: Int) -> Int {
        var i = end
        while i > floor, !chars[i - 1].isWhitespace { i -= 1 }
        while i > floor, chars[i - 1].isWhitespace { i -= 1 }
        return i
    }
}
