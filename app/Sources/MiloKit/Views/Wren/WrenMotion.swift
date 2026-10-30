import Foundation

/// A short authored move laid over the springs: a hop, a nod, a tail tick. Each track is a curve of
/// offsets through keys (seconds, value), starting and ending at zero so a clip never pops in or out.
struct WrenClip: Equatable {
    struct Key: Equatable {
        var at: Double
        var value: Double
    }

    enum Mode: Equatable {
        /// Added to the pose after the springs: exact timing, for moves the clip itself shapes.
        case add
        /// Added to where the springs head, so they soften it and overshoot: for slow weight shifts.
        case target
    }

    var name: String
    var mode = Mode.add
    var tracks: [WrenChannel: [Key]]

    init(_ name: String, mode: Mode = .add, _ tracks: [WrenChannel: [(Double, Double)]]) {
        self.name = name
        self.mode = mode
        self.tracks = tracks.mapValues { $0.map { Key(at: $0.0, value: $0.1) } }
    }

    var duration: Double { tracks.values.compactMap { $0.last?.at }.max() ?? 0 }

    /// The offset on `channel` at `t` seconds in. Between keys the curve is a Catmull-Rom spline, so it
    /// flows through them; it leaves the first key and lands on the last at rest.
    func value(_ channel: WrenChannel, at t: Double) -> Double {
        guard let keys = tracks[channel], let first = keys.first, let last = keys.last else { return 0 }
        if t <= first.at { return first.value }
        if t >= last.at { return last.value }
        let i = keys.firstIndex { $0.at > t }! - 1
        let a = keys[i], b = keys[i + 1]
        let span = b.at - a.at
        guard span > 0 else { return b.value }
        let u = (t - a.at) / span
        func slope(_ j: Int) -> Double {
            guard j > 0, j < keys.count - 1 else { return 0 }
            let p = keys[j - 1], n = keys[j + 1]
            return (n.value - p.value) / (n.at - p.at) * span
        }
        let m0 = slope(i), m1 = slope(i + 1)
        let u2 = u * u, u3 = u2 * u
        return (2 * u3 - 3 * u2 + 1) * a.value + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * b.value + (u3 - u2) * m1
    }

    /// The same move facing the other way: horizontal channels change sign.
    func mirrored(_ side: Double) -> WrenClip {
        guard side < 0 else { return self }
        var clip = self
        for channel in [WrenChannel.lean, .headTilt, .headX, .gazeX, .turn, .scarf] {
            clip.tracks[channel] = clip.tracks[channel]?.map { Key(at: $0.at, value: -$0.value) }
        }
        return clip
    }
}

/// Moves Milo's pose toward a target with one spring per channel, plays clips over it, blinks, flaps,
/// and lets the loose parts (scarf, tail, head) be thrown about by the body's motion. Pure and stepped
/// by the caller, so tests and renders can replay any moment.
struct WrenMotion {
    /// Where the springs are heading.
    var target = WrenPose.rest
    /// The pose to draw.
    private(set) var pose = WrenPose.rest
    private(set) var time = 0.0

    private var value: [Double]
    private var velocity: [Double]
    private var clips: [(clip: WrenClip, start: Double)] = []
    private var blinkStart: Double?
    private var flapPhase = 0.0
    /// The knot's sideways and the body's upward motion last substep, for the forces on the loose parts.
    private var last: (x: Double, y: Double, lean: Double)?
    private var lastSpeed = (x: 0.0, y: 0.0, lean: 0.0)

    static let step = 1.0 / 240

    /// Each channel's spring as stiffness and damping per unit mass.
    private static let stiffness = WrenChannel.allCases.map { pow(2 * .pi / $0.spring.response, 2) }
    private static let damping = WrenChannel.allCases.map { 4 * .pi * $0.spring.damping / $0.spring.response }

    /// Blink: shut in 70 ms, held 40 ms, open again in 120 ms.
    static let blinkTimes = (close: 0.07, hold: 0.04, open: 0.12)

    init(pose: WrenPose = .rest) {
        target = pose
        self.pose = pose
        value = WrenChannel.allCases.map { pose[$0] }
        velocity = Array(repeating: 0, count: WrenChannel.allCases.count)
    }

    var playing: [String] { clips.map(\.clip.name) }

    /// Nothing moving and nothing due: the view can stop asking for frames.
    var settled: Bool {
        guard clips.isEmpty, blinkStart == nil, !flapping else { return false }
        let aim = aimed()
        return WrenChannel.allCases.allSatisfy { c in
            abs(value[c.rawValue] - aim[c]) < c.epsilon && abs(velocity[c.rawValue]) < c.epsilon * 8
        }
    }

    private var flapping: Bool { target.fly > 0.5 || value[WrenChannel.fly.rawValue] > 0.05 }

    mutating func play(_ clip: WrenClip) {
        clips.removeAll { $0.clip.name == clip.name }
        clips.append((clip, time))
    }

    mutating func stop(_ name: String) {
        clips.removeAll { $0.clip.name == name }
    }

    mutating func blink() {
        if let start = blinkStart, time - start < Self.blinkTimes.close + Self.blinkTimes.hold { return }
        blinkStart = time
    }

    /// Jumps straight to the target, dropping anything in flight.
    mutating func snap() {
        clips.removeAll()
        blinkStart = nil
        last = nil
        for c in WrenChannel.allCases {
            value[c.rawValue] = target[c]
            velocity[c.rawValue] = 0
        }
        pose = output()
    }

    mutating func advance(by dt: Double) {
        var left = min(dt, 0.1)
        while left > 1e-9 {
            let h = min(Self.step, left)
            substep(h)
            left -= h
        }
        clips.removeAll { time - $0.start > $0.clip.duration }
        if let start = blinkStart, time - start > Self.blinkTimes.close + Self.blinkTimes.hold + Self.blinkTimes.open {
            blinkStart = nil
        }
        if settled {
            let aim = aimed()
            for c in WrenChannel.allCases {
                value[c.rawValue] = aim[c]
                velocity[c.rawValue] = 0
            }
            last = nil
        }
        pose = output()
    }

    // MARK: Inside

    /// The target with `.target` clips added.
    private func aimed() -> WrenPose {
        var aim = target
        for (clip, start) in clips where clip.mode == .target {
            for channel in clip.tracks.keys { aim[channel] += clip.value(channel, at: time - start) }
        }
        return aim
    }

    private mutating func substep(_ h: Double) {
        time += h
        let aim = aimed()
        for c in WrenChannel.allCases {
            let i = c.rawValue
            let a = -Self.stiffness[i] * (value[i] - aim[c]) - Self.damping[i] * velocity[i]
            velocity[i] += a * h
        }
        throwLooseParts(h)
        for i in value.indices { value[i] += velocity[i] * h }
        if flapping { flapPhase += h * 2 * .pi * 4.6 }
    }

    /// The scarf end swings like a pendulum when the knot is thrown sideways or up; the tail whips the
    /// other way; the head lags the body's lean and settles after it (overlapping action).
    private mutating func throwLooseParts(_ h: Double) {
        let now = output(raw: true)
        let knotX = 100 + 52 * sin(now.turn * 50 * .pi / 180 + 32 * .pi / 180) + 60 * now.lean * .pi / 180 + now.headX * 0.3
        let up = now.lift + now.squash * 40
        defer { last = (knotX, up, now.lean) }
        guard let last else { lastSpeed = (0, 0, 0); return }
        let speed = (x: (knotX - last.x) / h, y: (up - last.y) / h, lean: (now.lean - last.lean) / h)
        let accel = (x: (speed.x - lastSpeed.x) / h, y: (speed.y - lastSpeed.y) / h, lean: (speed.lean - lastSpeed.lean) / h)
        lastSpeed = speed
        // Clamp: a pop in the target would otherwise fling the scarf round his neck.
        func clamp(_ v: Double, _ m: Double) -> Double { min(m, max(-m, v)) }
        let ax = clamp(accel.x, 4000), ay = clamp(accel.y, 6000), al = clamp(accel.lean, 3000)
        velocity[WrenChannel.scarf.rawValue] += (ax * 2.6 - ay * 0.18) * h
        velocity[WrenChannel.tail.rawValue] += (-ay * 0.16 + ax * 0.35 * (now.turn > 0 ? -1 : 1)) * h
        velocity[WrenChannel.headTilt.rawValue] += -al * 0.5 * h
        velocity[WrenChannel.headY.rawValue] += ay * 0.012 * h
    }

    /// The spring values with the `.add` clips, the blink and the flap laid on top.
    private func output(raw: Bool = false) -> WrenPose {
        var p = WrenPose.rest
        for c in WrenChannel.allCases { p[c] = value[c.rawValue] }
        for (clip, start) in clips where clip.mode == .add {
            for channel in clip.tracks.keys { p[channel] += clip.value(channel, at: time - start) }
        }
        if raw { return p }
        if let start = blinkStart {
            let t = time - start, b = Self.blinkTimes
            let shut: Double
            if t < b.close { shut = WrenRig.smooth(0, 1, t / b.close) }
            else if t < b.close + b.hold { shut = 1 }
            else { shut = 1 - WrenRig.smooth(0, 1, (t - b.close - b.hold) / b.open) }
            p.lidL += (1 - p.lidL) * shut
            p.lidR += (1 - p.lidR) * shut
            p.browL -= 0.12 * shut
            p.browR -= 0.12 * shut
        }
        let fly = value[WrenChannel.fly.rawValue]
        if fly > 0.05 {
            // Wingbeats: a fast downstroke, a slower recovery; the body bobs against them.
            let s = sin(flapPhase), w = WrenRig.smooth(0.05, 0.6, fly)
            let beat = s > 0 ? s : s * 0.75
            p.wingL += beat * 34 * w
            p.wingR += beat * 34 * w
            p.lift += -cos(flapPhase) * 2.2 * w
            p.squash += sin(flapPhase + 0.6) * 0.025 * w
            p.scarf += sin(flapPhase - 1.2) * 7 * w
        }
        p.lidL = min(1, max(0, p.lidL)); p.lidR = min(1, max(0, p.lidR))
        p.lowerL = min(1, max(0, p.lowerL)); p.lowerR = min(1, max(0, p.lowerR))
        p.beak = min(1, max(0, p.beak))
        p.blush = min(1, max(0, p.blush))
        p.openL = min(1, max(0, p.openL)); p.openR = min(1, max(0, p.openR))
        p.fly = min(1, max(0, p.fly)); p.feet = min(1, max(0, p.feet))
        p.scarfToss = min(1.1, max(-0.1, p.scarfToss)); p.scarfUp = min(1, max(0, p.scarfUp))
        return p
    }
}
