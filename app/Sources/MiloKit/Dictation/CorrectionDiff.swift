import Foundation

/// One fix the user made to words Milo pasted: Whisper wrote `heard`, they meant `meant`. A few words each.
public struct DictationFix: Equatable, Sendable {
    public var heard: String
    public var meant: String

    public init(heard: String, meant: String) {
        self.heard = heard
        self.meant = meant
    }
}

/// Whether a word is in the Mac's dictionaries. Tells a mishearing ("teh" for "the") from a change of mind
/// ("their" for "there", "car" for "cat"), which only fits that one sentence.
public protocol WordList: AnyObject {
    func isWord(_ word: String) -> Bool
}

/// Finds the small fixes in what the user did to a pasted text (ADR 21). Pure: the words in, the fixes out.
///
/// The pasted words and the edited ones are aligned word by word, punctuation at a word's edges aside. A rewrite
/// (over half the words changed) teaches nothing. Inserted words (typed after the span, a new thought) and deleted
/// ones (a sentence removed) are skipped. What's left are substitutions; one counts as a fix when it is 1 to 3
/// words for 1 to 3 words, spelled alike, and not just a capital at a sentence start.
public enum CorrectionDiff {
    public static let maxPastedWords = 200
    public static let maxWordsPerSide = 3
    public static let maxFixes = 8
    /// The share of the longer side's letters that may differ (edit distance). "Cloud" to "Claude" is 2 of 6.
    public static let maxDifference = 0.5

    /// Words that are easy to mishear for each other but that people change on purpose: a fix between two of
    /// them is a change of plan, never learned ("Monday" to "Sunday").
    static let calendarWords: Set<String> = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
        "november", "december",
        "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
        "januar", "februar", "märz", "juni", "juli", "oktober", "dezember",
        "today", "tomorrow", "yesterday", "heute", "morgen", "gestern",
    ]

    public static func fixes(pasted: String, edited: String, words: WordList) -> [DictationFix] {
        let before = tokens(pasted), after = tokens(edited)
        guard !before.isEmpty, !after.isEmpty, before.count <= maxPastedWords, after.count <= 2 * maxPastedWords + 50
        else { return [] }
        let matches = align(before.map(\.text), after.map(\.text))
        let removed = before.count - matches.count
        guard removed <= max(3, before.count / 2) else { return [] }  // a rewrite

        var fixes: [DictationFix] = []
        var previous = (-1, -1)
        for match in matches + [(before.count, after.count)] {
            let heardRange = (previous.0 + 1)..<match.0, meantRange = (previous.1 + 1)..<match.1
            if let fix = fix(before, heardRange, after, meantRange, matched: Set(matches.map(\.1)), words: words),
               !fixes.contains(fix) {
                fixes.append(fix)
            }
            previous = match
        }
        return Array(fixes.prefix(maxFixes))
    }

    // MARK: One substitution

    private static func fix(_ before: [Token], _ heardRange: Range<Int>, _ after: [Token], _ edited: Range<Int>,
                            matched: Set<Int>, words: WordList) -> DictationFix? {
        guard !heardRange.isEmpty, !edited.isEmpty else { return nil }
        // Words that only changed case at the hunk's edges ("and the" to "The": a sentence split) aren't part of
        // the substitution. If nothing else is left on one side, the change was a deletion or an insertion.
        var heardRange = heardRange, edited = edited
        let whole = (heardRange, edited)
        while !heardRange.isEmpty, !edited.isEmpty,
              before[heardRange.lowerBound].text.lowercased() == after[edited.lowerBound].text.lowercased() {
            heardRange = (heardRange.lowerBound + 1)..<heardRange.upperBound
            edited = (edited.lowerBound + 1)..<edited.upperBound
        }
        while !heardRange.isEmpty, !edited.isEmpty,
              before[heardRange.upperBound - 1].text.lowercased() == after[edited.upperBound - 1].text.lowercased() {
            heardRange = heardRange.lowerBound..<(heardRange.upperBound - 1)
            edited = edited.lowerBound..<(edited.upperBound - 1)
        }
        if heardRange.isEmpty != edited.isEmpty { return nil }
        if heardRange.isEmpty { (heardRange, edited) = whole }  // only the case changed: "github" to "GitHub"
        guard heardRange.count <= maxWordsPerSide else { return nil }
        let heard = before[heardRange].map(\.text).joined(separator: " ")
        // At the span's end the user may have fixed the last word and typed on ("Cloud" to "Claude, see you"),
        // at its start typed something before it: the fix is then the words nearest the paste.
        var candidates = [edited]
        if edited.upperBound == after.count, edited.count > heardRange.count {
            candidates.append(edited.lowerBound..<(edited.lowerBound + heardRange.count))
        }
        if edited.lowerBound == 0, edited.count > heardRange.count {
            candidates.append((edited.upperBound - heardRange.count)..<edited.upperBound)
        }
        guard let meantRange = candidates.first(where: { range in
            range.count <= maxWordsPerSide && similar(heard, after[range].map(\.text).joined(separator: " "))
        }) else { return nil }
        let meant = after[meantRange].map(\.text).joined(separator: " ")
        let atStart = startsSentence(after, meantRange.lowerBound) || startsSentence(before, heardRange.lowerBound)
        if atStart, firstLetterCaseOnly(heard, meant) { return nil }  // "the" to "The": the user split a sentence
        guard !changeOfMind(heard, meant, words: words) else { return nil }
        // A name: "Cloud Code" to "Claude Code" is learned whole, not as "Cloud" to "Claude", which would also
        // change "the cloud".
        var lower = meantRange.lowerBound, upper = meantRange.upperBound
        var heardWords = before[heardRange].map(\.text), meantWords = after[meantRange].map(\.text)
        if heardRange.count == 1, meantRange.count == 1, meant.first?.isUppercase == true {
            if lower > 0, matched.contains(lower - 1), partOfName(after, lower - 1) {
                lower -= 1
                heardWords.insert(after[lower].text, at: 0)
                meantWords.insert(after[lower].text, at: 0)
            }
            if !after[upper - 1].endsSentence, upper < after.count, matched.contains(upper), partOfName(after, upper) {
                heardWords.append(after[upper].text)
                meantWords.append(after[upper].text)
                upper += 1
            }
        }
        return DictationFix(heard: heardWords.joined(separator: " "), meant: meantWords.joined(separator: " "))
    }

    /// Spelled alike: the same letters and digits up to `maxDifference`, ignoring case, spaces and punctuation.
    static func similar(_ heard: String, _ meant: String) -> Bool {
        let a = folded(heard), b = folded(meant)
        guard !a.isEmpty, b.count >= 2 else { return false }
        if a == b { return true }  // case, spaces or punctuation inside: "github" to "GitHub", "Mac Book" to "MacBook"
        guard !(a.allSatisfy(\.isNumber) && b.allSatisfy(\.isNumber)) else { return false }  // "15" to "16"
        return Double(distance(a, b)) <= Double(max(a.count, b.count)) * maxDifference
    }

    /// Changes that fit only this sentence: two calendar words, or a lowercase fix whose heard words are all real
    /// words ("their" to "there", "cat" to "car"). A real word for a misspelling ("teh" to "the") still counts.
    static func changeOfMind(_ heard: String, _ meant: String, words: WordList) -> Bool {
        if calendarWords.contains(heard.lowercased()), calendarWords.contains(meant.lowercased()) { return true }
        guard !meant.contains(where: \.isUppercase), folded(heard) != folded(meant) else { return false }
        return heard.split(separator: " ").allSatisfy { words.isWord(String($0)) }
    }

    private static func firstLetterCaseOnly(_ heard: String, _ meant: String) -> Bool {
        heard != meant && heard.dropFirst() == meant.dropFirst() && heard.prefix(1).lowercased() == meant.prefix(1).lowercased()
    }

    private static func startsSentence(_ tokens: [Token], _ index: Int) -> Bool {
        index == 0 || tokens[index - 1].endsSentence
    }

    /// A capitalized word in the middle of a sentence: likely part of the same name. "I" is not.
    private static func partOfName(_ tokens: [Token], _ index: Int) -> Bool {
        let text = tokens[index].text
        return text.first?.isUppercase == true && text != "I" && !startsSentence(tokens, index)
    }

    // MARK: Words

    struct Token {
        /// The word without punctuation at its edges: "Code," is "Code", "e-mail" stays.
        var text: String
        var endsSentence: Bool
    }

    static func tokens(_ text: String) -> [Token] {
        text.split(whereSeparator: \.isWhitespace).compactMap { raw in
            let word = raw.trimmingCharacters(in: CharacterSet.punctuationCharacters.union(.symbols))
            guard !word.isEmpty else { return nil }
            return Token(text: word, endsSentence: raw.last.map { ".!?".contains($0) } ?? false)
        }
    }

    static func folded(_ text: String) -> [Character] {
        Array(text.lowercased().filter { $0.isLetter || $0.isNumber })
    }

    /// The matched word pairs of a longest common subsequence, in order. At most 200 by 450 words: 90,000 cells.
    static func align(_ a: [String], _ b: [String]) -> [(Int, Int)] {
        let n = a.count, m = b.count
        var table = [[Int]](repeating: [Int](repeating: 0, count: m + 1), count: n + 1)
        for i in stride(from: n - 1, through: 0, by: -1) {
            for j in stride(from: m - 1, through: 0, by: -1) {
                table[i][j] = a[i] == b[j] ? table[i + 1][j + 1] + 1 : max(table[i + 1][j], table[i][j + 1])
            }
        }
        var pairs: [(Int, Int)] = []
        var i = 0, j = 0
        while i < n, j < m {
            if a[i] == b[j] {
                pairs.append((i, j))
                i += 1
                j += 1
            } else if table[i + 1][j] >= table[i][j + 1] {
                i += 1
            } else {
                j += 1
            }
        }
        return pairs
    }

    /// Edits from one to the other, where swapping two neighbouring letters is one edit ("teh" to "the").
    static func distance(_ a: [Character], _ b: [Character]) -> Int {
        guard !a.isEmpty, !b.isEmpty else { return max(a.count, b.count) }
        var d = [[Int]](repeating: [Int](repeating: 0, count: b.count + 1), count: a.count + 1)
        for i in 0...a.count { d[i][0] = i }
        for j in 0...b.count { d[0][j] = j }
        for i in 1...a.count {
            for j in 1...b.count {
                d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1))
                if i > 1, j > 1, a[i - 1] == b[j - 2], a[i - 2] == b[j - 1] {
                    d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
                }
            }
        }
        return d[a.count][b.count]
    }
}
