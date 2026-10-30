import Foundation

/// Watches the words Milo just pasted, and reports the small fixes the user makes to them (ADR 21).
///
/// A while after the paste it reads the focused field and finds the pasted words before the caret, then reads
/// it again every `poll` and keeps the span's latest text. The watch ends after `window`, when the focus moves
/// to another field, when the span is gone (the message was sent, the paste undone), or when Milo pastes
/// somewhere else. Then the span's last text is compared with what was pasted; only the fixes go out. The
/// field's text stays here, and only for the watch.
public final class PasteWatcher {
    public struct Timing: Sendable {
        /// From the paste to the first read: the Cmd-V Milo posts lands a moment later.
        public var firstRead: TimeInterval
        public var poll: TimeInterval
        public var window: TimeInterval

        public init(firstRead: TimeInterval = 0.3, poll: TimeInterval = 0.5, window: TimeInterval = 45) {
            self.firstRead = firstRead
            self.poll = poll
            self.window = window
        }
    }

    /// Gets the fixes of one watch, never empty.
    public var onFixes: (([DictationFix]) -> Void)?

    private let reader: FocusedTextReader
    private let words: WordList
    private let scheduler: Scheduler
    private let timing: Timing
    private var waiting: (text: String, task: ScheduledTask)?
    private var watch: Watch?
    /// Answers to reads started for an earlier watch are dropped.
    private var generation = 0

    private struct Watch {
        var field: Int
        var span: PastedSpan
        var latest: String
        var polls: Int
        var timer: ScheduledTask
    }

    public init(reader: FocusedTextReader, words: WordList, scheduler: Scheduler, timing: Timing = Timing()) {
        self.reader = reader
        self.words = words
        self.scheduler = scheduler
        self.timing = timing
    }

    /// Milo pasted `text` into the focused app. Pastes that come before the first read are read together.
    public func pasted(_ text: String) {
        let text = (waiting?.text ?? "") + text
        waiting?.task.cancel()
        waiting = (text, scheduler.after(timing.firstRead) { [weak self] in self?.readPaste() })
    }

    /// Stop watching without learning anything (learning was switched off).
    public func stop() {
        waiting?.task.cancel()
        waiting = nil
        watch?.timer.cancel()
        watch = nil
        generation += 1
    }

    private func readPaste() {
        guard let text = waiting?.text else { return }
        waiting = nil
        let generation = generation
        reader.read { [weak self] snapshot in
            guard let self, generation == self.generation else { return }
            self.landed(text, snapshot)
        }
    }

    private func landed(_ text: String, _ snapshot: FocusedText?) {
        guard let snapshot else { return finish() }
        if var current = watch, current.field == snapshot.field,
           current.span.extend(with: text, value: snapshot.value, caret: snapshot.caret),
           let found = current.span.find(in: snapshot.value) {
            current.latest = found.text
            current.polls = 0  // the window runs from the newest paste
            watch = current
            return
        }
        finish()
        guard let span = PastedSpan(pasted: text, value: snapshot.value, caret: snapshot.caret) else { return }
        let timer = scheduler.every(timing.poll) { [weak self] in self?.poll() }
        watch = Watch(field: snapshot.field, span: span, latest: span.pasted, polls: 0, timer: timer)
    }

    private func poll() {
        guard var current = watch else { return }
        current.polls += 1
        watch = current
        if Double(current.polls) * timing.poll >= timing.window { return finish() }
        let generation = generation
        reader.read { [weak self] snapshot in
            guard let self, generation == self.generation, var current = self.watch else { return }
            guard let snapshot, snapshot.field == current.field, let found = current.span.find(in: snapshot.value),
                  !found.text.allSatisfy(\.isWhitespace)
            else { return self.finish() }
            current.latest = found.text
            current.span.found(at: found.range)
            self.watch = current
        }
    }

    /// Compare what the span last held with what was pasted, and send the fixes.
    private func finish() {
        guard let done = watch else { return }
        watch = nil
        done.timer.cancel()
        generation += 1
        let fixes = CorrectionDiff.fixes(pasted: done.span.pasted, edited: done.latest, words: words)
        if !fixes.isEmpty { onFixes?(fixes) }
    }
}
