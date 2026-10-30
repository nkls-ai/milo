import AppKit
import Combine
import QuartzCore

/// Flies the overlay panel to the corner of `MiloModel.workingWindow` while Milo works in it, else to
/// `MiloModel.flyTarget`, and home again when both clear. It moves the whole
/// window along an arc, 60 times a second while he is in the air and not at all otherwise, and keeps
/// `MiloModel.flight` up to date so the figure flaps and points.
final class FlightDriver {
    private weak var panel: NSWindow?
    private let model: MiloModel
    /// Milo's centre in the panel, in points from its bottom-left corner.
    private let center: CGPoint
    /// Where the panel was before the first flight; the user may have dragged him there.
    private var home: NSPoint?
    private var timer: Timer?
    private var watch: AnyCancellable?

    init(panel: NSWindow, model: MiloModel, center: CGPoint) {
        self.panel = panel
        self.model = model
        self.center = center
        watch = model.$workingWindow.combineLatest(model.$flyTarget)
            .map { Goal(window: $0, point: $1) }
            .removeDuplicates()
            .sink { [weak self] in self?.go(to: $0) }
    }

    private struct Goal: Equatable {
        var window: CGRect?
        var point: CGPoint?
    }

    private var perchedOn: CGRect?

    private func go(to goal: Goal) {
        guard let panel else { return }
        if let window = goal.window {
            if home == nil { home = panel.frame.origin }
            let corner = CGPoint(x: window.maxX, y: window.maxY)
            let screen = NSScreen.screens.first { $0.frame.contains(corner) } ?? panel.screen ?? NSScreen.main
            guard let visible = screen?.visibleFrame else { return }
            let perch = FlightPlan.perch(onCornerOf: window, within: visible)
            let origin = NSPoint(x: perch.center.x - center.x, y: perch.center.y - center.y)
            // Dragged along with the window: he holds on instead of flying again.
            if perchedOn != nil, timer == nil, hypot(origin.x - panel.frame.minX, origin.y - panel.frame.minY) < 160 {
                panel.setFrameOrigin(origin)
                perchedOn = window
                return set(.pointing(toward: perch.toward))
            }
            perchedOn = window
            fly(to: origin) { [weak self] in self?.set(.pointing(toward: perch.toward)) }
            return
        }
        perchedOn = nil
        if let target = goal.point {
            if home == nil { home = panel.frame.origin }
            let screen = NSScreen.screens.first { $0.frame.contains(target) } ?? panel.screen ?? NSScreen.main
            guard let visible = screen?.visibleFrame else { return }
            let perch = FlightPlan.perch(pointingAt: target, within: visible)
            fly(to: NSPoint(x: perch.center.x - center.x, y: perch.center.y - center.y)) { [weak self] in
                self?.set(.pointing(toward: perch.toward))
            }
        } else if let home {
            self.home = nil
            fly(to: home) { [weak self] in self?.set(.perched) }
        }
    }

    private func fly(to end: NSPoint, then arrive: @escaping () -> Void) {
        guard let panel else { return }
        timer?.invalidate()
        timer = nil
        let start = panel.frame.origin
        let distance = hypot(end.x - start.x, end.y - start.y)
        if distance < 1 || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            panel.setFrameOrigin(end)
            arrive()
            return
        }
        let duration = FlightPlan.duration(distance)
        let began = CACurrentMediaTime()
        var last = start
        let timer = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] timer in
            guard let self, let panel = self.panel else { return timer.invalidate() }
            let t = min(1, (CACurrentMediaTime() - began) / duration)
            let p = FlightPlan.point(from: start, to: end, at: t)
            panel.setFrameOrigin(p)
            if t >= 1 {
                timer.invalidate()
                self.timer = nil
                return arrive()
            }
            guard hypot(p.x - last.x, p.y - last.y) > 0.5 else { return }
            let heading = FlightPlan.direction(from: last, to: p)
            last = p
            // Fifths, so the figure redraws when the heading really turns, not every frame.
            set(.flying(heading: CGVector(dx: (heading.dx * 5).rounded() / 5, dy: (heading.dy * 5).rounded() / 5)))
        }
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    private func set(_ flight: Flight) {
        if model.flight != flight { model.flight = flight }
    }
}
