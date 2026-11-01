// Decides Milo's performance (WrenDirector.swift): from what the figure is told, the pose he holds and the moves he
// makes on the way in and while he holds it. Pure: time comes in with each call, randomness from a seed.
//
// An input is { state, emotion, asleep, level, connected, words, asking, working, noting, pose, flight }:
//   state    "idle" | "listening" | "dictating" | "transcribing" | "thinking" | "speaking"
//   emotion  "neutral" | "happy" | "excited" | "thinking" | "concerned" | "sad" | "sleepy" | "confused"
//   pose     the life layer's pose (life.mjs)
//   flight   { kind: "perched" } | { kind: "flying", dx, dy } | { kind: "pointing", dx, dy }
import * as Pose from "./pose.mjs"
import * as Clips from "./clips.mjs"
import { SeededRandom } from "./random.mjs"
import { restPose as restLife } from "./life.mjs"

// A nod at most this often, so a fast talker doesn't make him bob like a toy.
const NOD_GAP = 0.7
const PERCHED = { kind: "perched" }

export function input(values) {
    return Object.assign({ state: "idle", emotion: "neutral", asleep: false, level: 0, connected: true, words: 0,
                           asking: false, working: false, noting: false, pose: restLife(), flight: PERCHED },
                         values || {})
}

// The feeling the face shows: sleepy while asleep, a smile while the cursor first arrives.
export function shown(i) {
    if (i.asleep && !i.pose.hovered) return "sleepy"
    if (i.pose.pleased && i.emotion === "neutral" && i.state === "idle") return "happy"
    return i.emotion
}

// Asleep with his eyes shut, not mid-yawn.
export const sleeping = i => shown(i) === "sleepy" && !i.pose.yawn

// Writing notes: taking them, perched, with nobody talking to him or waiting on an answer.
export const writing = i => i.noting && i.state === "idle" && !i.asking && i.flight.kind === "perched"

const thinkingState = s => s === "thinking" || s === "transcribing"

// The pose Milo holds for `i`. Everything here is a destination; springs get him there.
export function pose(i) {
    const p = Pose.rest()
    const life = i.pose
    const s = life.side
    const emotion = shown(i)
    const asleep = emotion === "sleepy" && !life.yawn
    const level = Pose.clamp(i.level, 0, 1)

    p.turn = 0.2 * s
    p.gazeX = life.gaze.dx
    p.gazeY = life.gaze.dy
    // a slight curious tilt toward the screen, even at rest
    p.headTilt = life.tilt + 3 * s
    p.squash = life.squash * 1.3
    p.lift = Math.max(0, life.squash) * 60

    switch (i.state) {
    case "listening":
        p.lean = 4 * s
        p.lidL = p.lidR = 0.06
        p.eyeL = p.eyeR = 1.06
        p.browL = p.browR = 0.35
        p.tail = 10 + level * 20
        p.tailFan = level
        p.crest = 0.6 + level * 0.4
        p.squash += 0.02
        break
    case "dictating":
        p.lean = 2.5 * s
        p.lidL = p.lidR = 0.14
        p.browL = p.browR = 0.15
        p.browTiltL = p.browTiltR = -0.1
        p.tail = 6 + level * 16
        p.tailFan = level * 0.8
        p.crest = 0.3 + level * 0.3
        p.gazeY += 0.2
        break
    case "thinking":
    case "transcribing":
        p.lidL = 0.28; p.lidR = 0.24
        // one brow up, the other down a touch: "hm"
        if (s < 0) { p.browL = 0.75; p.browR = -0.1; p.browTiltR = -0.3 } else { p.browR = 0.75; p.browL = -0.1; p.browTiltL = -0.3 }
        p.headTilt += -6 * s
        p.tail = 4
        p.crest = 0.25
        break
    case "speaking":
        p.beak = Math.pow(Math.min(1, level * 1.25), 0.8)
        p.browL = p.browR = 0.15 + level * 0.35
        p.headY = -level * 1.6
        p.lidL = p.lidR = 0.14
        p.squash -= level * 0.025
        p.tail = 6
        p.crest = 0.15 + level * 0.25
        break
    }

    if (i.working) {
        p.lidL = p.lidR = 0.3
        p.browL = p.browR = -0.15
        p.browTiltL = p.browTiltR = -0.25
        p.scarfToss = 1
        p.tail = Math.max(p.tail, 4)
        p.crest = Math.max(p.crest, 0.2)
    }
    if (i.noting && i.flight.kind === "perched") {
        // The notepad up in both wings. Idle, his eyes are on it; talking with the user, they're on them.
        p.pad = 1
        p.wingL = p.wingR = -16
        // the scarf's end flipped aside, out of the way of the page
        p.scarfToss = Math.max(p.scarfToss, 0.4)
        p.crest = Math.max(p.crest, 0.3)
        p.tail = Math.max(p.tail, 8)
        if (i.state === "idle" && !i.asking) {
            p.gazeY = 0.6
            p.gazeX = 0.15 * s
            p.headY += 1.8
            p.headTilt += 4 * s
            p.lidL = p.lidR = 0.26
            p.browL = p.browR = 0.2
        }
    }
    if (i.asking) {
        p.headTilt += 9 * s
        p.lidL = p.lidR = 0.05
        p.eyeL = p.eyeR = 1.08
        p.browL = p.browR = 0.45
        p.browTiltL = p.browTiltR = 0.2
        p.tail = 16
        p.tailFan = 0.4
        p.crest = Math.max(p.crest, 0.5)
    }

    switch (emotion) {
    case "happy":
        p.lowerL = p.lowerR = 1
        p.lidL = p.lidR = 0.2
        p.blush = 0.8
        p.tail += 12
        p.crest = Math.max(p.crest, 0.4)
        p.browL = p.browR = 0.35
        p.squash += 0.02
        break
    case "excited":
        p.lidL = p.lidR = 0
        p.eyeL = p.eyeR = 1.12
        p.beak = Math.max(p.beak, 0.3)
        p.blush = 0.75
        p.tail += 20
        p.tailFan = Math.max(p.tailFan, 0.7)
        p.crest = 1
        p.browL = p.browR = 0.6
        p.wingL = p.wingR = 12
        break
    case "thinking":
        if (!thinkingState(i.state)) {
            p.lidL = 0.28; p.lidR = 0.24
            if (s < 0) { p.browL = 0.75; p.browR = -0.1 } else { p.browR = 0.75; p.browL = -0.1 }
        }
        break
    case "concerned":
        p.browTiltL = p.browTiltR = 1
        p.browL = p.browR = 0.1
        p.lidL = p.lidR = 0.3
        p.tail -= 8
        p.crest = -0.3
        p.wingL = p.wingR = -4
        p.lean -= 2 * s
        p.squash -= 0.02
        p.headTilt -= 3 * s
        break
    case "sad":
        p.lidL = p.lidR = 0.45
        p.browTiltL = p.browTiltR = 0.8
        p.browL = p.browR = -0.2
        p.tail -= 16
        p.crest = -0.8
        p.squash -= 0.04
        p.headY += 3
        p.gazeY = Math.max(p.gazeY, 0.45)
        p.wingL = p.wingR = -4
        break
    case "confused":
        p.headTilt += -10 * s
        if (s < 0) { p.browR = 0.7; p.browL = -0.25; p.browTiltL = -0.3 } else { p.browL = 0.7; p.browR = -0.25; p.browTiltR = -0.3 }
        p.lidL = s < 0 ? 0.3 : 0.12; p.lidR = s < 0 ? 0.12 : 0.3
        p.gazeX -= 0.3 * s
        p.crest = 0.4
        break
    case "sleepy":
        if (asleep) {
            p.lidL = p.lidR = 1
            p.lowerL = p.lowerR = 0
            p.scarfUp = 1
            p.headY = 2.5
            p.headTilt = 5 * s
            p.squash = -0.06
            p.tail = -12
            p.crest = -1
            p.gazeX = p.gazeY = 0
            p.browL = p.browR = -0.1
            p.wingL = p.wingR = -3
        } else {
            p.lidL = p.lidR = 0.45
            p.crest = -0.5
        }
        break
    }

    if (life.yawn) {
        p.beak = 1
        p.lidL = p.lidR = 0.8
        p.lowerL = p.lowerR = 0.35
        p.headTilt = -6 * s
        p.headY = -3
        p.squash = 0.05
        p.wingL = p.wingR = 16
        p.browL = p.browR = 0.3
    }

    const f = i.flight
    if (f.kind === "flying") {
        p.fly = 1
        if (Math.abs(f.dx) > 0.15) p.turn = f.dx > 0 ? 0.3 : -0.3
        p.lean = f.dx * 12
        p.headTilt = f.dx * 6
        p.gazeX = f.dx * 0.7
        p.gazeY = f.dy * 0.4
        p.feet = 0
        p.wingL = p.wingR = 40
        p.lidL = p.lidR = 0.08
        p.browL = p.browR = 0.3
        p.tail = 0; p.tailFan = 1
        p.crest = -0.4
        p.lift = 0; p.squash = 0
    } else if (f.kind === "pointing") {
        p.turn = f.dx < 0 ? -0.2 : 0.2
        p.gazeX = f.dx * 0.85
        p.gazeY = f.dy * 0.85
        p.headX = f.dx * 2
        p.headY = f.dy * 2
        p.lean = f.dx * 4
        if (!i.working) {
            // the wing on that side spread and held toward the spot, like a hand
            const r = f.dx < 0 ? Math.atan2(-f.dy, -f.dx) : -Math.atan2(f.dy, f.dx)
            const angle = Pose.clamp(r * 180 / Math.PI, -50, 70)
            if (f.dx < 0) { p.wingL = angle; p.openL = 1 } else { p.wingR = angle; p.openR = 1 }
            p.browL = Math.max(p.browL, 0.3); p.browR = Math.max(p.browR, 0.3)
        }
    }
    return p
}

// The pose a still figure shows: where the springs would come to rest, with the eyes shut mid-blink.
export function stillPose(i) {
    const p = pose(i)
    if (i.pose.blink) p.lidL = p.lidR = 1
    return p
}

const GLAD = ["happy", "excited"]

// The moves a change of input calls for.
export function cues(a, b, s) {
    const clips = []
    const ea = shown(a), eb = shown(b)
    const fa = a.flight.kind, fb = b.flight.kind

    // flight first: it overrides the rest
    if (fa !== "flying" && fb === "flying") return [Clips.takeoff, Clips.holdOff]
    if (fa === "flying" && fb !== "flying") clips.push(Clips.land)

    if (eb === "sleepy" && !b.pose.yawn && !(ea === "sleepy" && !a.pose.yawn)) clips.push(Clips.settle)
    else if (ea === "sleepy" && eb !== "sleepy") clips.push(Clips.mirrored(Clips.ruffle, s))
    if (GLAD.includes(eb) && !GLAD.includes(ea)) {
        clips.push(a.working || a.state === "thinking" ? Clips.proud : Clips.hop)
        clips.push(eb === "excited" ? Clips.fluffUp : Clips.wiggle)
        if (eb === "excited") clips.push(Clips.flutter)
    } else if (eb === "excited" && ea !== "excited") {
        clips.push(Clips.flutter)
    }
    if (eb === "concerned" && ea !== "concerned") clips.push(Clips.mirrored(Clips.flinch, -s))
    if (eb === "sad" && ea !== "sad") clips.push(Clips.deflate)
    if (eb === "confused" && ea !== "confused") {
        clips.push(Clips.mirrored(Clips.doubleTake, -s))
        clips.push(Clips.fluffUp)
    }

    if (b.state !== a.state) {
        switch (b.state) {
        case "listening": clips.push(Clips.perk); break
        case "dictating": clips.push(Clips.nod); break
        case "speaking": clips.push(Clips.inhale); break
        case "thinking": case "transcribing": clips.push(Clips.mirrored(Clips.hmm, s)); break
        case "idle": if (a.state === "speaking") clips.push(Clips.settle); break
        }
    }
    if (b.asking && !a.asking) { clips.push(Clips.tailTick); clips.push(Clips.perk) }
    if (b.working && !a.working) clips.push(Clips.rollUp)
    if (b.noting && !a.noting) clips.push(Clips.perk)
    if (a.noting && !b.noting) clips.push(Clips.settle)

    const habit = b.pose.habit
    if (habit && habit !== a.pose.habit) {
        switch (habit) {
        case "tailFlick": clips.push(Clips.tailFlick); break
        case "bob": clips.push(Clips.bob); break
        case "scarfTug": clips.push(Clips.scarfTug(s)); break
        case "ruffle": clips.push(Clips.mirrored(Clips.ruffle, s)); break
        case "wingStretch": clips.push(Clips.wingStretch(s)); break
        }
    }
    if (b.pose.squash > 0.06 && a.pose.squash <= 0.06 && !b.pose.habit && !b.pose.yawn && b.state === "idle"
        && b.pose.squash < 0.085) {
        // the life layer's stretch: a wing goes with it
        clips.push(Clips.wingStretch(s))
    }
    return clips
}

export class Director {
    constructor(seed) {
        this.last = null
        this.rng = new SeededRandom(seed === undefined ? 1 : seed)
        // The next beat of a state's own rhythm: a gesture while speaking, a tap while thinking.
        this.beat = Infinity
        this.lastNod = -Infinity
        this.beats = 0
    }

    // When the director next wants to act without new input.
    get wake() { return this.beat }

    // Sets the motion's target for `i` and starts the moves its changes call for.
    direct(i, motion, now, reduceMotion) {
        motion.target = pose(i)
        const before = this.last
        this.last = i
        if (!before) return
        if (i.pose.blink && !before.pose.blink) motion.blink()
        if (reduceMotion) { this.beat = Infinity; return }
        for (const clip of cues(before, i, i.pose.side)) motion.play(clip)

        const speaking = i.state === "speaking"
        const thinking = thinkingState(i.state)
        const rng = this.rng
        if (i.words > before.words && (i.state === "listening" || i.state === "dictating") && now - this.lastNod > NOD_GAP) {
            this.lastNod = now
            motion.play(Clips.nod)
        }
        const notes = writing(i)
        const rhythm = speaking || thinking || i.asking || notes
        const wasRhythm = before.state === i.state && before.asking === i.asking && writing(before) === notes
        if (!rhythm) {
            this.beat = Infinity
        } else if (!wasRhythm || this.beat === Infinity) {
            this.beats = 0
            this.beat = now + (speaking ? rng.between(1.2, 2.2) : i.asking ? 2.8 : notes ? rng.between(0.6, 1.2)
                               : rng.between(0.9, 1.5))
        }
        if (now >= this.beat) {
            this.beats += 1
            const near = i.pose.side
            if (notes) {
                // A few lines of writing, then a look up at the call, as if someone said something worth noting.
                if (this.beats % 4 === 0) {
                    motion.play(Clips.mirrored(Clips.glanceUp, near))
                    this.beat = now + rng.between(2.4, 3.4)
                } else {
                    motion.play(Clips.scribble)
                    this.beat = now + rng.between(2, 3)
                }
            } else if (i.asking) {
                motion.play(Clips.tailTick)
                this.beat = now + rng.between(3.2, 4.6)
            } else if (speaking) {
                motion.play(rng.chance(0.5) ? Clips.gesture(near) : Clips.emphasis)
                this.beat = now + rng.between(2.2, 4)
            } else {
                motion.play(this.beats % 4 === 0 ? Clips.bob : Clips.tap)
                this.beat = now + rng.between(1.1, 1.6)
            }
        }
    }
}
