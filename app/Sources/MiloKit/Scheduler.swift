import Foundation

public protocol ScheduledTask: AnyObject {
    func cancel()
}

/// Runs work later on the main queue. Injected so tests can advance time by hand.
public protocol Scheduler: AnyObject {
    @discardableResult func after(_ delay: TimeInterval, _ work: @escaping () -> Void) -> ScheduledTask
    @discardableResult func every(_ interval: TimeInterval, _ work: @escaping () -> Void) -> ScheduledTask
}

public final class MainQueueScheduler: Scheduler {
    public init() {}

    public func after(_ delay: TimeInterval, _ work: @escaping () -> Void) -> ScheduledTask {
        let item = DispatchWorkItem(block: work)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: item)
        return WorkItemTask(item: item)
    }

    public func every(_ interval: TimeInterval, _ work: @escaping () -> Void) -> ScheduledTask {
        let timer = Timer(timeInterval: interval, repeats: true) { _ in work() }
        RunLoop.main.add(timer, forMode: .default)
        return TimerTask(timer: timer)
    }

    private final class WorkItemTask: ScheduledTask {
        let item: DispatchWorkItem
        init(item: DispatchWorkItem) { self.item = item }
        func cancel() { item.cancel() }
    }

    private final class TimerTask: ScheduledTask {
        let timer: Timer
        init(timer: Timer) { self.timer = timer }
        func cancel() { timer.invalidate() }
    }
}
