// Moves Milo's pose toward a target with one spring per channel, plays clips over it, blinks, flaps, and lets the
// loose parts (scarf, tail, head) be thrown about by the body's motion (WrenMotion.swift). Pure and stepped by the
// caller, so tests and stills can replay any moment.
import * as Pose from "./pose.mjs"
import * as Clips from "./clips.mjs"

const STEP = 1 / 240
// Blink: shut in 70 ms, held 40 ms, open again in 120 ms.
export const BLINK = { close: 0.07, hold: 0.04, open: 0.12 }

const N = Pose.CHANNELS.length
const STIFFNESS = Pose.CHANNELS.map(c => Math.pow(2 * Math.PI / Pose.response(c), 2))
const DAMPING = Pose.CHANNELS.map(c => 4 * Math.PI * Pose.damping(c) / Pose.response(c))
const INDEX = {}
Pose.CHANNELS.forEach((c, i) => { INDEX[c] = i })

export class Motion {
    constructor(pose) {
        const start = pose || Pose.rest()
        this.target = Pose.copy(start)
        this.time = 0
        this.value = Pose.CHANNELS.map(c => start[c])
        this.velocity = new Array(N).fill(0)
        this.clips = []
        this.blinkStart = null
        this.flapPhase = 0
        this.last = null
        this.lastSpeed = { x: 0, y: 0, lean: 0 }
        this.pose = this.output(false)
    }

    get playing() { return this.clips.map(c => c.clip.name) }

    // Nothing moving and nothing due: the view can stop asking for frames.
    get settled() {
        if (this.clips.length || this.blinkStart !== null || this.flapping) return false
        const aim = this.aimed()
        for (let i = 0; i < N; ++i) {
            const c = Pose.CHANNELS[i], e = Pose.epsilon(c)
            if (Math.abs(this.value[i] - aim[c]) >= e || Math.abs(this.velocity[i]) >= e * 8) return false
        }
        return true
    }

    get flapping() { return this.target.fly > 0.5 || this.value[INDEX.fly] > 0.05 }

    play(clip) {
        this.clips = this.clips.filter(c => c.clip.name !== clip.name)
        this.clips.push({ clip, start: this.time })
    }

    stop(name) { this.clips = this.clips.filter(c => c.clip.name !== name) }

    blink() {
        if (this.blinkStart !== null && this.time - this.blinkStart < BLINK.close + BLINK.hold) return
        this.blinkStart = this.time
    }

    // Jumps straight to the target, dropping anything in flight.
    snap() {
        this.clips = []
        this.blinkStart = null
        this.last = null
        for (let i = 0; i < N; ++i) {
            this.value[i] = this.target[Pose.CHANNELS[i]]
            this.velocity[i] = 0
        }
        this.pose = this.output(false)
    }

    advance(dt) {
        let left = Math.min(dt, 0.1)
        while (left > 1e-9) {
            const h = Math.min(STEP, left)
            this.substep(h)
            left -= h
        }
        this.clips = this.clips.filter(c => this.time - c.start <= c.clip.duration)
        if (this.blinkStart !== null && this.time - this.blinkStart > BLINK.close + BLINK.hold + BLINK.open)
            this.blinkStart = null
        if (this.settled) {
            const aim = this.aimed()
            for (let i = 0; i < N; ++i) {
                this.value[i] = aim[Pose.CHANNELS[i]]
                this.velocity[i] = 0
            }
            this.last = null
        }
        this.pose = this.output(false)
    }

    // The target with "target" clips added.
    aimed() {
        const aim = Pose.copy(this.target)
        for (const { clip, start } of this.clips) {
            if (clip.mode !== "target") continue
            for (const ch in clip.tracks) aim[ch] += Clips.value(clip, ch, this.time - start)
        }
        return aim
    }

    substep(h) {
        this.time += h
        const aim = this.aimed()
        for (let i = 0; i < N; ++i) {
            const a = -STIFFNESS[i] * (this.value[i] - aim[Pose.CHANNELS[i]]) - DAMPING[i] * this.velocity[i]
            this.velocity[i] += a * h
        }
        this.throwLooseParts(h)
        for (let i = 0; i < N; ++i) this.value[i] += this.velocity[i] * h
        if (this.flapping) this.flapPhase += h * 2 * Math.PI * 4.6
    }

    // The scarf end swings like a pendulum when the knot is thrown sideways or up; the tail whips the other way; the
    // head lags the body's lean and settles after it; the tuft sways behind the head and is pressed flat as he goes
    // up, then springs back (overlapping action).
    throwLooseParts(h) {
        const now = this.output(true)
        const knotX = 100 + 52 * Math.sin((now.turn * 50 + 32) * Math.PI / 180) + 60 * now.lean * Math.PI / 180
                      + now.headX * 0.3
        const up = now.lift + now.squash * 40
        const last = this.last
        this.last = { x: knotX, y: up, lean: now.lean }
        if (!last) { this.lastSpeed = { x: 0, y: 0, lean: 0 }; return }
        const speed = { x: (knotX - last.x) / h, y: (up - last.y) / h, lean: (now.lean - last.lean) / h }
        const accel = { x: (speed.x - this.lastSpeed.x) / h, y: (speed.y - this.lastSpeed.y) / h,
                        lean: (speed.lean - this.lastSpeed.lean) / h }
        this.lastSpeed = speed
        // Clamped: a pop in the target would otherwise fling the scarf round his neck.
        const ax = Pose.clamp(accel.x, -4000, 4000), ay = Pose.clamp(accel.y, -6000, 6000)
        const al = Pose.clamp(accel.lean, -3000, 3000)
        const v = this.velocity
        v[INDEX.scarf] += (ax * 2.6 - ay * 0.18) * h
        v[INDEX.tail] += (-ay * 0.16 + ax * 0.35 * (now.turn > 0 ? -1 : 1)) * h
        v[INDEX.headTilt] += -al * 0.5 * h
        v[INDEX.headY] += ay * 0.012 * h
        v[INDEX.crestSway] += (-ax * 1.6 - al * 0.9) * h
        v[INDEX.crest] += -ay * 0.004 * h
    }

    // The spring values with the "add" clips, the blink and the flap laid on top.
    output(raw) {
        const p = {}
        for (let i = 0; i < N; ++i) p[Pose.CHANNELS[i]] = this.value[i]
        for (const { clip, start } of this.clips) {
            if (clip.mode !== "add") continue
            for (const ch in clip.tracks) p[ch] += Clips.value(clip, ch, this.time - start)
        }
        if (raw) return p
        if (this.blinkStart !== null) {
            const t = this.time - this.blinkStart, b = BLINK
            const shut = t < b.close ? Pose.smooth(0, 1, t / b.close)
                       : t < b.close + b.hold ? 1
                       : 1 - Pose.smooth(0, 1, (t - b.close - b.hold) / b.open)
            p.lidL += (1 - p.lidL) * shut
            p.lidR += (1 - p.lidR) * shut
            p.browL -= 0.12 * shut
            p.browR -= 0.12 * shut
        }
        const fly = this.value[INDEX.fly]
        if (fly > 0.05) {
            // Wingbeats: a fast downstroke, a slower recovery; the body bobs against them.
            const s = Math.sin(this.flapPhase), w = Pose.smooth(0.05, 0.6, fly)
            const beat = s > 0 ? s : s * 0.75
            p.wingL += beat * 34 * w
            p.wingR += beat * 34 * w
            p.lift += -Math.cos(this.flapPhase) * 2.2 * w
            p.squash += Math.sin(this.flapPhase + 0.6) * 0.025 * w
            p.scarf += Math.sin(this.flapPhase - 1.2) * 7 * w
        }
        for (const ch of ["lidL", "lidR", "lowerL", "lowerR", "beak", "blush", "openL", "openR", "fly", "feet",
                          "scarfUp"])
            p[ch] = Pose.clamp(p[ch], 0, 1)
        p.scarfToss = Pose.clamp(p.scarfToss, -0.1, 1.1)
        return p
    }
}
