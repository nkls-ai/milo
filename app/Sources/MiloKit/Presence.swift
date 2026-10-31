import Combine
import CoreGraphics
import Foundation

/// Whether Milo is on screen. With nothing going on for `hideAfter` seconds he hops up and flies off the bottom-right
/// edge; anything that needs him brings him straight back the way he went: a key, a word from him, a question, work,
/// a meeting, the menu bar. `OverlayPanel` orders the panel out while he is away and in again as he comes back.
public final class Presence: ObservableObject {
    public enum Phase: Equatable, Sendable {
        case here
        /// On his way off since that moment, on the presence's clock. `plain`: Reduce Motion, a fade only.
        case leaving(since: TimeInterval, plain: Bool)
        case away
        /// On his way back since that moment.
        case arriving(since: TimeInterval, plain: Bool)

        /// Between perch and gone, so the overlay draws every frame.
        public var moving: Bool {
            switch self {
            case .leaving, .arriving: true
            case .here, .away: false
            }
        }
    }

    @Published public private(set) var phase: Phase = .here

    /// `[ui] hide_after_s` until the brain says otherwise.
    public static let defaultHideAfter: TimeInterval = 15
    /// Seconds with nothing going on before he leaves; nil: he stays on screen. A change counts from now.
    public var hideAfter: TimeInterval? = Presence.defaultHideAfter {
        didSet {
            guard hideAfter != oldValue else { return }
            if hideAfter == nil {
                stopCountdown()
                come()
            } else if present && !needed {
                countDown()
            }
        }
    }

    /// The user drags him: he stays put. Set by the panel.
    public var held = false {
        didSet { if held != oldValue { check() } }
    }

    /// The pointer rests on him: he waits until it moves off, looking again every `pointerWait` seconds. Asked only
    /// when the wait is over, so a pointer that left without a word can't keep him for good. Set by the panel.
    public var pointing: () -> Bool = { false }
    static let pointerWait: TimeInterval = 3

    /// Reduce Motion, read as he sets off. Set by the panel.
    public var reduceMotion: () -> Bool = { false }

    /// Seconds on the model's monotonic clock.
    public let now: () -> TimeInterval
    private let scheduler: Scheduler
    private var model: () -> Bool = { false }
    private var countdown: ScheduledTask?
    private var step: ScheduledTask?
    private var pending: ScheduledTask?
    private var watches: [AnyCancellable] = []
    private var wasNeeded = false

    init(scheduler: Scheduler, clock: @escaping () -> TimeInterval) {
        self.scheduler = scheduler
        now = clock
    }

    /// Follows the model: any change is looked at a moment later, once it is in (`objectWillChange` fires before).
    func watch(_ model: MiloModel) {
        self.model = { [weak model] in model.map(Self.needs) ?? false }
        let changed = model.objectWillChange.merge(with: model.meeting.objectWillChange, model.done.objectWillChange)
        watches = [changed.sink { [weak self] _ in self?.soon() }]
        check()
    }

    /// What Milo is doing or showing that the user may need: he stays for it, and comes back for it.
    /// Being offline isn't one: a brain that is gone for good would keep him up forever.
    public static func needs(_ m: MiloModel) -> Bool {
        if m.state != .idle || m.question != nil || m.bubble != nil || m.canStop { return true }
        if let phase = m.voicePhase, phase != .offline { return true }
        if m.ear != nil || m.handsFree != nil || m.handsActive || m.handsBorrowed || m.looking { return true }
        if m.helpers.contains(where: \.status.active) { return true }
        if m.recording || m.meeting.status.live || m.meeting.status.phase == .writing { return true }
        if !m.done.cards.isEmpty { return true }
        return m.workingWindow != nil || m.flyTarget != nil || m.flight != .perched
    }

    private var needed: Bool { held || model() }

    /// Nothing needs him: "Hide Milo" may send him off.
    public var canLeave: Bool { !needed }

    /// The user asked for him (the menu bar, a click on him): back now, and the wait starts over.
    public func summon() {
        come()
        if !needed { countDown() }
    }

    /// "Hide Milo": off now, unless something needs him.
    public func dismiss() {
        guard !needed else { return }
        stopCountdown()
        leave()
    }

    // MARK: Deciding

    private func soon() {
        guard pending == nil else { return }
        pending = scheduler.after(0) { [weak self] in
            self?.pending = nil
            self?.check()
        }
    }

    private func check() {
        let need = needed
        defer { wasNeeded = need }
        if need {
            stopCountdown()
            return come()
        }
        // The wait starts when the last thing that needed him is over, or once he is back.
        if present && (wasNeeded || countdown == nil) { countDown() }
    }

    /// On screen or on his way back.
    private var present: Bool {
        if case .arriving = phase { return true }
        return phase == .here
    }

    private func countDown(_ wait: TimeInterval? = nil) {
        stopCountdown()
        guard let delay = wait ?? hideAfter, hideAfter != nil else { return }
        countdown = scheduler.after(delay) { [weak self] in
            guard let self else { return }
            countdown = nil
            guard !needed else { return }
            if pointing() { return countDown(Self.pointerWait) }
            leave()
        }
    }

    private func stopCountdown() {
        countdown?.cancel()
        countdown = nil
    }

    // MARK: Going and coming

    /// Seconds he crouches before he springs, as before a flight (`FlightDriver.crouch`).
    static let crouch: TimeInterval = 0.16
    static let flightTime: TimeInterval = 0.62
    static let fadeTime: TimeInterval = 0.25

    static func leaveDuration(plain: Bool) -> TimeInterval { plain ? fadeTime : crouch + flightTime }
    static func arriveDuration(plain: Bool) -> TimeInterval { plain ? fadeTime : flightTime }

    private func leave() {
        let t = now()
        switch phase {
        case .here:
            set(.leaving(since: t, plain: reduceMotion()))
        case let .arriving(since, plain):
            // Turns round where he is: the way back is the way off, run backwards.
            let done = min(1, (t - since) / Self.arriveDuration(plain: plain))
            let lead = plain ? 0 : Self.crouch
            set(.leaving(since: t - lead - (1 - done) * (Self.leaveDuration(plain: plain) - lead), plain: plain))
        case .leaving, .away:
            return
        }
        finish(after: Self.leaveDuration(plain: plain(phase)) - (t - since(phase))) { [weak self] in
            self?.set(.away)
        }
    }

    private func come() {
        let t = now()
        switch phase {
        case .away:
            set(.arriving(since: t, plain: reduceMotion()))
        case let .leaving(since, plain):
            let lead = plain ? 0 : Self.crouch
            let gone = max(0, min(1, (t - since - lead) / (Self.leaveDuration(plain: plain) - lead)))
            set(.arriving(since: t - (1 - gone) * Self.arriveDuration(plain: plain), plain: plain))
        case .here, .arriving:
            return
        }
        finish(after: Self.arriveDuration(plain: plain(phase)) - (t - since(phase))) { [weak self] in
            guard let self else { return }
            set(.here)
            wasNeeded = false
            check()
        }
    }

    private func finish(after delay: TimeInterval, _ work: @escaping () -> Void) {
        step?.cancel()
        step = scheduler.after(max(0, delay), work)
    }

    private func set(_ new: Phase) {
        if phase != new { phase = new }
    }

    private func since(_ phase: Phase) -> TimeInterval {
        switch phase {
        case let .leaving(since, _), let .arriving(since, _): since
        case .here, .away: now()
        }
    }

    private func plain(_ phase: Phase) -> Bool {
        switch phase {
        case let .leaving(_, plain), let .arriving(_, plain): plain
        case .here, .away: false
        }
    }

    // MARK: How he looks on the way

    /// Milo at `time` on the presence's clock.
    public func pose(at time: TimeInterval) -> Pose {
        switch phase {
        case .here: Pose()
        case .away: Pose(opacity: 0)
        case let .leaving(since, plain): Pose.leaving(time - since, plain: plain)
        case let .arriving(since, plain): Pose.arriving(time - since, plain: plain)
        }
    }

    /// One moment of his way off the screen or back: how far from his perch he is (view points, y down), how much of
    /// him shows, and the heading the wren flies with (nil: whatever the model says, usually perched).
    public struct Pose: Equatable, Sendable {
        public var offset: CGSize = .zero
        public var opacity: Double = 1
        public var heading: CGVector?

        /// Where the way off ends: past the panel's bottom-right corner, all of him out of it.
        static let gone = CGPoint(x: 140, y: 180)
        /// Pulls the start of the way up: he hops about 30 points before he dives, and on the way back swoops up past
        /// his perch and settles down onto it.
        static let hop = CGPoint(x: 30, y: -110)

        /// `elapsed` seconds into leaving. He crouches with his wings ready (the wren's takeoff), then springs up
        /// a little and dives off, faster and faster, fading as he reaches the edge.
        static func leaving(_ elapsed: TimeInterval, plain: Bool) -> Pose {
            if plain { return Pose(opacity: 1 - unit(elapsed / fadeTime)) }
            return along(unit((elapsed - crouch) / flightTime), back: false)
        }

        /// `elapsed` seconds into coming back: the way off run backwards, so he swoops in fast and brakes onto his
        /// perch, where the wren lands.
        static func arriving(_ elapsed: TimeInterval, plain: Bool) -> Pose {
            if plain { return Pose(opacity: unit(elapsed / fadeTime)) }
            return along(1 - unit(elapsed / flightTime), back: true)
        }

        /// `u` 0...1 of the way off in time. Eased in: he leaves slowly and is fastest at the edge.
        private static func along(_ u: Double, back: Bool) -> Pose {
            let s = pow(u, 1.6)
            let a = 1 - s
            let x = 2 * a * s * hop.x + s * s * gone.x
            let y = 2 * a * s * hop.y + s * s * gone.y
            // the tangent of the curve, pointing the way he flies
            var dx = 2 * a * hop.x + 2 * s * (gone.x - hop.x)
            var dy = 2 * a * hop.y + 2 * s * (gone.y - hop.y)
            if back { dx = -dx; dy = -dy }
            let length = max(0.001, hypot(dx, dy))
            // Fifths, so the figure is told when the heading really turns, not every frame.
            let heading = CGVector(dx: ((dx / length) * 5).rounded() / 5, dy: ((dy / length) * 5).rounded() / 5)
            // Fading from where he passes his perch on the way down, gone before the panel's edge cuts much of him.
            let opacity = 1 - unit((s - 0.55) / 0.33)
            return Pose(offset: CGSize(width: x, height: y), opacity: opacity, heading: heading)
        }

        private static func unit(_ v: Double) -> Double { min(1, max(0, v)) }
    }
}
