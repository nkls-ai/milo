import Foundation
@testable import MiloKit

final class FakeBrainClient: BrainClient {
    var onEvent: ((BrainEvent) -> Void)?
    var onConnectionChange: ((Bool) -> Void)?
    var answers = true
    private(set) var started = false
    private(set) var sent: [BrainCommand] = []

    func probe() -> Bool { answers }
    func start() { started = true }
    func send(_ command: BrainCommand) { sent.append(command) }

    func emit(_ event: BrainEvent) { onEvent?(event) }
    func connect(_ up: Bool = true) { onConnectionChange?(up) }
    func clearSent() { sent.removeAll() }
}

final class FakeBrainLauncher: BrainLauncher {
    private(set) var starts = 0
    private(set) var stops = 0
    private(set) var restarts = 0
    func start() { starts += 1 }
    func stop() { stops += 1 }
    func restart() { restarts += 1 }
}

final class FakeTextInserter: TextInserter {
    private(set) var inserted: [String] = []
    private(set) var copied: [String] = []
    func insert(_ text: String) { inserted.append(text) }
    func copy(_ text: String) { copied.append(text) }
}

final class FakeKeySource: KeyEventSource {
    var onEvent: ((KeyEvent) -> Void)?
    private(set) var started = false
    func start() { started = true }

    func press(_ key: ModifierKey, at time: TimeInterval) {
        onEvent?(KeyEvent(.modifierChanged(keyCode: key.keyCode, isDown: true), at: time))
    }

    func release(_ key: ModifierKey, at time: TimeInterval) {
        onEvent?(KeyEvent(.modifierChanged(keyCode: key.keyCode, isDown: false), at: time))
    }

    func type(at time: TimeInterval) {
        onEvent?(KeyEvent(.keyDown, at: time))
    }

    func send(_ event: KeyEvent) { onEvent?(event) }
}

final class FakeContextProvider: ContextProvider {
    var onAppSwitch: (() -> Void)?
    var context = AppContext(app: "Xcode", idleSeconds: 3.5)
    func current() -> AppContext { context }
    func switchApp(to name: String) {
        context.app = name
        onAppSwitch?()
    }
}

final class FakeAccessibility: AccessibilityPermission {
    var trusted = true
    private(set) var prompts: [Bool] = []
    func isTrusted(prompt: Bool) -> Bool {
        prompts.append(prompt)
        return trusted
    }
}

/// A scheduler whose clock moves only when the test calls `advance(by:)`.
final class ManualScheduler: Scheduler {
    private final class Task: ScheduledTask {
        var due: TimeInterval
        let interval: TimeInterval?
        let work: () -> Void
        var cancelled = false
        init(due: TimeInterval, interval: TimeInterval?, work: @escaping () -> Void) {
            self.due = due
            self.interval = interval
            self.work = work
        }
        func cancel() { cancelled = true }
    }

    private(set) var now: TimeInterval = 0
    private var tasks: [Task] = []

    /// Tasks that will still run, one-shot or repeating.
    var pendingCount: Int { tasks.filter { !$0.cancelled }.count }

    func after(_ delay: TimeInterval, _ work: @escaping () -> Void) -> ScheduledTask {
        add(Task(due: now + delay, interval: nil, work: work))
    }

    func every(_ interval: TimeInterval, _ work: @escaping () -> Void) -> ScheduledTask {
        add(Task(due: now + interval, interval: interval, work: work))
    }

    /// Runs everything due up to `now + seconds`, in time order.
    func advance(by seconds: TimeInterval) {
        let end = now + seconds
        while true {
            tasks.removeAll(where: \.cancelled)
            guard let next = tasks.filter({ $0.due <= end }).min(by: { $0.due < $1.due }) else { break }
            now = next.due
            if let interval = next.interval { next.due += interval } else { next.cancelled = true }
            next.work()
        }
        now = end
    }

    private func add(_ task: Task) -> Task {
        tasks.append(task)
        return task
    }
}

final class FakeConnections: AppConnections {
    var outcome: AppOutcome = .success(.array([]))
    private(set) var handled: [(op: String, args: JSONValue)] = []
    func handle(op: String, args: JSONValue, reply: @escaping (AppOutcome) -> Void) {
        handled.append((op, args))
        reply(outcome)
    }
}
