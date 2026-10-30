import Foundation

/// Where Milo's pasted words sit in a text field, found again after the user edits in and around them (ADR 21).
///
/// Right after the paste the words end at the caret. The text just before and just after them is kept as
/// anchors; later the span is whatever lies between the two. Offsets are UTF-16, as Accessibility counts them.
struct PastedSpan: Equatable {
    /// What was pasted, from its first word on (a typed phrase comes with a leading space).
    private(set) var pasted: String
    private let before: String
    private let after: String
    /// Where the span began when it was last found; picks among repeats of `before`.
    private var start: Int

    /// Characters kept on each side. An edit inside them loses the span; shorter anchors match elsewhere more often.
    static let anchor = 24

    /// nil when the field doesn't hold `text` right before the caret: the app changed it, or the paste hasn't
    /// landed yet.
    init?(pasted text: String, value: String, caret: Int) {
        let words = String(text.drop(while: \.isWhitespace))
        let field = value as NSString
        let length = (words as NSString).length
        let start = caret - length
        guard length > 0, start >= 0, caret <= field.length,
              field.substring(with: NSRange(location: start, length: length)) == words else { return nil }
        pasted = words
        self.start = start
        let lead = max(0, start - Self.anchor)
        before = field.substring(with: NSRange(location: lead, length: start - lead))
        after = field.substring(with: NSRange(location: caret, length: min(Self.anchor, field.length - caret)))
    }

    /// The span's range and text in the field's value now. nil when an anchor is gone, or the span grew far beyond
    /// what was pasted (the user wrote on and on, or the anchors match some other place).
    func find(in value: String) -> (range: NSRange, text: String)? {
        let field = value as NSString
        var lower = 0
        if !before.isEmpty {
            guard let end = nearestEnd(of: before, in: field, to: start) else { return nil }
            lower = end
        }
        var upper = field.length
        if !after.isEmpty {
            let found = field.range(of: after, options: .literal,
                                    range: NSRange(location: lower, length: field.length - lower))
            guard found.location != NSNotFound else { return nil }
            upper = found.location
        }
        let length = (pasted as NSString).length
        guard upper - lower <= max(3 * length, length + 200) else { return nil }
        let range = NSRange(location: lower, length: upper - lower)
        return (range, field.substring(with: range))
    }

    /// Another paste landed right at the span's end (dictation that types phrase by phrase): the span takes it in.
    /// false if it went anywhere else.
    mutating func extend(with text: String, value: String, caret: Int) -> Bool {
        guard let found = find(in: value), NSMaxRange(found.range) == caret, found.text.hasSuffix(text) else {
            return false
        }
        pasted += text
        start = found.range.location
        return true
    }

    mutating func found(at range: NSRange) {
        start = range.location
    }

    private func nearestEnd(of anchor: String, in field: NSString, to position: Int) -> Int? {
        var best: Int?
        var from = 0
        for _ in 0..<50 {
            let found = field.range(of: anchor, options: .literal, range: NSRange(location: from, length: field.length - from))
            guard found.location != NSNotFound else { break }
            let end = NSMaxRange(found)
            if best.map({ abs(end - position) < abs($0 - position) }) ?? true { best = end }
            from = found.location + 1
        }
        return best
    }
}
