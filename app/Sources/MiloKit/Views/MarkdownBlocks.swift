import SwiftUI

/// Markdown as blocks the window can lay out: the small part of Markdown Milo's notes use (headings, paragraphs,
/// bullets, numbered items, checkboxes, quotes, rules, code). Inline styles (bold, italics, code, links) are left to
/// `AttributedString`. Its own, so the app needs no dependency (docs/research/meeting-notes-ux.md).
public enum MarkdownBlock: Equatable, Sendable {
    case heading(level: Int, text: String)
    case paragraph(String)
    /// `depth` 0 for the outer list, 1 for an item indented under it.
    case bullet(String, depth: Int)
    case numbered(Int, String, depth: Int)
    case todo(done: Bool, String, depth: Int)
    case quote(String)
    case code(String)
    case rule

    /// Splits `markdown` into blocks. Lines of one paragraph join with a space; a blank line ends it.
    public static func parse(_ markdown: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        var paragraph: [String] = []
        var quote: [String] = []
        var code: [String]?

        func flush() {
            if !paragraph.isEmpty { blocks.append(.paragraph(paragraph.joined(separator: " "))) }
            if !quote.isEmpty { blocks.append(.quote(quote.joined(separator: " "))) }
            paragraph = []
            quote = []
        }

        for raw in markdown.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n") {
            if var lines = code {
                if raw.trimmingCharacters(in: .whitespaces).hasPrefix("```") {
                    blocks.append(.code(lines.joined(separator: "\n")))
                    code = nil
                } else {
                    lines.append(raw)
                    code = lines
                }
                continue
            }
            let line = raw.trimmingCharacters(in: .whitespaces)
            let depth = min(1, raw.prefix { $0 == " " || $0 == "\t" }.reduce(0) { $0 + ($1 == "\t" ? 4 : 1) } / 2)
            if line.isEmpty { flush(); continue }
            if line.hasPrefix("```") { flush(); code = []; continue }
            if let heading = Self.heading(line) { flush(); blocks.append(heading); continue }
            if line.count >= 3, Set(line.filter { $0 != " " }) == ["-"] || Set(line.filter { $0 != " " }) == ["*"] {
                flush(); blocks.append(.rule); continue
            }
            if line.hasPrefix(">") {
                if !paragraph.isEmpty { flush() }
                quote.append(String(line.dropFirst()).trimmingCharacters(in: .whitespaces))
                continue
            }
            if let item = Self.item(line, depth: depth) { flush(); blocks.append(item); continue }
            if !quote.isEmpty { flush() }
            // A line under a list item, indented, goes on with that item.
            if depth > 0, paragraph.isEmpty, let last = blocks.last, let joined = Self.continued(last, with: line) {
                blocks[blocks.count - 1] = joined
                continue
            }
            paragraph.append(line)
        }
        if let lines = code { blocks.append(.code(lines.joined(separator: "\n"))) }
        flush()
        return blocks
    }

    private static func heading(_ line: String) -> MarkdownBlock? {
        let hashes = line.prefix { $0 == "#" }.count
        guard (1...6).contains(hashes), line.dropFirst(hashes).first == " " else { return nil }
        return .heading(level: hashes, text: line.dropFirst(hashes).trimmingCharacters(in: .whitespaces))
    }

    private static func item(_ line: String, depth: Int) -> MarkdownBlock? {
        for mark in ["- ", "* ", "+ "] where line.hasPrefix(mark) {
            let rest = String(line.dropFirst(2))
            let lower = rest.lowercased()
            if lower.hasPrefix("[ ] ") || lower.hasPrefix("[x] ") {
                return .todo(done: lower.hasPrefix("[x]"), String(rest.dropFirst(4)), depth: depth)
            }
            return .bullet(rest, depth: depth)
        }
        let digits = line.prefix { $0.isNumber }
        if !digits.isEmpty, digits.count < 4, let n = Int(digits) {
            let rest = line.dropFirst(digits.count)
            if rest.hasPrefix(". ") || rest.hasPrefix(") ") {
                return .numbered(n, String(rest.dropFirst(2)), depth: depth)
            }
        }
        return nil
    }

    private static func continued(_ block: MarkdownBlock, with line: String) -> MarkdownBlock? {
        switch block {
        case let .bullet(text, depth): .bullet(text + " " + line, depth: depth)
        case let .numbered(n, text, depth): .numbered(n, text + " " + line, depth: depth)
        case let .todo(done, text, depth): .todo(done: done, text + " " + line, depth: depth)
        default: nil
        }
    }

    /// Inline Markdown as styled text; the plain text when it doesn't parse.
    public static func inline(_ text: String) -> AttributedString {
        (try? AttributedString(markdown: text, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(text)
    }
}

/// Markdown blocks laid out in Milo's type: headings in his rounded face, bullets as small dots, to-dos as boxes.
/// Selectable; links open through the environment's `openURL`, so a page can catch its own.
struct MarkdownView: View {
    @Environment(\.miloTheme) private var theme
    let blocks: [MarkdownBlock]
    var size: CGFloat = 13.5

    init(_ markdown: String, size: CGFloat = 13.5) {
        blocks = MarkdownBlock.parse(markdown)
        self.size = size
    }

    init(blocks: [MarkdownBlock], size: CGFloat = 13.5) {
        self.blocks = blocks
        self.size = size
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { index, block in
                view(block)
                    .padding(.top, index == 0 ? 0 : gap(before: block, after: blocks[index - 1]))
            }
        }
        .textSelection(.enabled)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func view(_ block: MarkdownBlock) -> some View {
        switch block {
        case let .heading(level, text):
            Text(MarkdownBlock.inline(text))
                .font(.system(size: level == 1 ? size + 8 : level == 2 ? size + 2.5 : size + 0.5,
                              weight: level <= 2 ? .bold : .semibold, design: .rounded))
                .foregroundStyle(theme.ink)
                .accessibilityAddTraits(.isHeader)
                .fixedSize(horizontal: false, vertical: true)
        case let .paragraph(text):
            prose(text)
        case let .bullet(text, depth):
            row(depth: depth) {
                Circle().fill(theme.primary.opacity(0.7)).frame(width: 5, height: 5)
            } content: { prose(text) }
        case let .numbered(n, text, depth):
            row(depth: depth) {
                Text("\(n).")
                    .font(.system(size: size, weight: .semibold, design: .rounded).monospacedDigit())
                    .foregroundStyle(theme.primary)
            } content: { prose(text) }
        case let .todo(done, text, depth):
            row(depth: depth) {
                Image(systemName: done ? "checkmark.square.fill" : "square")
                    .font(.system(size: size, weight: .medium))
                    .foregroundStyle(done ? theme.primary : theme.ink.opacity(0.5))
                    .accessibilityLabel(done ? "Done" : "To do")
            } content: {
                prose(text).opacity(done ? 0.6 : 1)
            }
        case let .quote(text):
            prose(text)
                .padding(.leading, 12)
                .overlay(alignment: .leading) { Capsule().fill(theme.primary.opacity(0.35)).frame(width: 3) }
        case let .code(text):
            Text(text)
                .font(.system(size: size - 1.5, design: .monospaced))
                .foregroundStyle(theme.ink.opacity(0.85))
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(theme.ink.opacity(0.05)))
        case .rule:
            Rectangle().fill(theme.rule).frame(height: 1).padding(.vertical, 4)
        }
    }

    private func prose(_ text: String) -> some View {
        Text(MarkdownBlock.inline(text))
            .font(.system(size: size))
            .lineSpacing(2.5)
            .foregroundStyle(theme.ink.opacity(0.92))
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// A list item: its mark in a fixed column on the first line, the words wrapping beside it.
    private func row(depth: Int, @ViewBuilder mark: () -> some View,
                     @ViewBuilder content: () -> some View) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            ZStack { Text(" ").font(.system(size: size)); mark() }
                .frame(width: 16)
            content()
        }
        .padding(.leading, CGFloat(depth) * 20)
    }

    /// Air between blocks: more before a heading, little between items of one list.
    private func gap(before block: MarkdownBlock, after previous: MarkdownBlock) -> CGFloat {
        switch (previous, block) {
        case (_, .heading(let level, _)): return level <= 2 ? 22 : 16
        case (.heading, _): return 8
        case (.bullet, .bullet), (.numbered, .numbered), (.todo, .todo), (.bullet, .todo), (.todo, .bullet): return 6
        default: return 11
        }
    }
}
