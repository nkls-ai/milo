import AppKit
import SwiftUI

/// Where the cursor is relative to Milo, read from the screen.
struct LifeSenses: Equatable {
    var cursor: CGPoint
    var towardCentre: Double
}

/// Runs `CharacterLife`: wakes only when the pose is due to change, and samples the cursor
/// while Milo is on screen (10 Hz awake, 4 Hz asleep, 1 Hz hidden). Publishes a pose only when it differs.
final class CharacterLifeDriver: ObservableObject {
    @Published private(set) var pose = LifePose()
    /// False while the window is hidden or covered, so the view can pause its float.
    @Published private(set) var onScreen = true

    /// Reads the cursor; nil while Milo isn't visible. Set by `LifeAnchor`.
    var sense: () -> LifeSenses? = { nil }

    private var life: CharacterLife
    private var input = LifeInput()
    private let scheduler: Scheduler
    private let clock: () -> Date
    private let origin: Date
    private var wakeTask: ScheduledTask?
    private var pollTask: ScheduledTask?
    private var pollInterval: TimeInterval = 0
    private var running = false

    init(scheduler: Scheduler = MainQueueScheduler(), clock: @escaping () -> Date = Date.init,
         seed: UInt64 = .random(in: 0...UInt64.max)) {
        self.scheduler = scheduler
        self.clock = clock
        origin = clock()
        life = CharacterLife(seed: seed)
    }

    func start() {
        guard !running else { return }
        running = true
        poll()
    }

    func stop() {
        running = false
        wakeTask?.cancel()
        pollTask?.cancel()
        wakeTask = nil
        pollTask = nil
        pollInterval = 0
    }

    func update(state: MiloState, asleep: Bool) {
        input.state = state
        input.asleep = asleep
        refresh()
    }

    private func poll() {
        guard running else { return }
        let senses = sense()
        input.cursor = senses?.cursor
        if let senses { input.towardCentre = senses.towardCentre }
        if onScreen != (senses != nil) { onScreen = senses != nil }
        refresh()
        let interval: TimeInterval = senses == nil ? 1 : (input.asleep ? 0.25 : 0.1)
        if interval != pollInterval {
            pollTask?.cancel()
            pollInterval = interval
            pollTask = scheduler.every(interval) { [weak self] in self?.poll() }
        }
    }

    private func refresh() {
        guard running else { return }
        let date = clock()
        let hour = Calendar.current.component(.hour, from: date)
        input.late = hour >= 23 || hour < 5
        let now = date.timeIntervalSince(origin)
        let next = life.update(input, at: now)
        if next != pose { pose = next }
        wakeTask?.cancel()
        wakeTask = nil
        if life.wake.isFinite {
            wakeTask = scheduler.after(max(0.01, life.wake - now)) { [weak self] in self?.refresh() }
        }
    }
}

/// An invisible view behind the character that tells the driver where Milo is on screen.
/// It never takes clicks, so dragging and clicking on Milo behave as before.
struct LifeAnchor: NSViewRepresentable {
    let driver: CharacterLifeDriver

    func makeNSView(context: Context) -> AnchorView {
        let view = AnchorView()
        driver.sense = { [weak view] in view?.senses() }
        return view
    }

    func updateNSView(_ view: AnchorView, context: Context) {}

    final class AnchorView: NSView {
        override func hitTest(_ point: NSPoint) -> NSView? { nil }

        func senses() -> LifeSenses? {
            guard let window, window.isVisible, window.occlusionState.contains(.visible) else { return nil }
            let rect = window.convertToScreen(convert(bounds, to: nil))
            let mouse = NSEvent.mouseLocation
            let middle = (window.screen ?? NSScreen.main)?.visibleFrame.midX ?? 0
            return LifeSenses(cursor: CGPoint(x: mouse.x - rect.midX, y: mouse.y - rect.midY),
                              towardCentre: middle < rect.midX ? -1 : 1)
        }
    }
}
