// Milo's idle life (CharacterLife.swift): gaze, blinks, glances, stretches, yawns, fidgets and a squash on state
// changes. Pure: time comes in through update(input, now), randomness from a seed, so tests can replay a day.
//
// A life input is { state, asleep, late, cursor, towardCentre }: `cursor` is the pointer relative to Milo's centre in
// points, y up (null when unknown), `towardCentre` -1 when the middle of the screen is to his left, 1 to his right.
import { SeededRandom } from "./random.mjs"

// The body in the same coordinates as the cursor.
const BODY = { x: -54, y: -50, width: 108, height: 112 }
// How long the eyes keep following a cursor that stopped moving.
const ATTENTION = 2.5

// How the body should look right now; the figure springs between these, so a pose only changes at moments.
export function restPose() {
    return { gaze: { dx: 0, dy: 0 }, lean: 0, squash: 0, tilt: 0, blink: false, yawn: false, hovered: false,
             pleased: false, habit: null, side: -1 }
}

export function samePose(a, b) {
    return a.gaze.dx === b.gaze.dx && a.gaze.dy === b.gaze.dy && a.lean === b.lean && a.squash === b.squash
        && a.tilt === b.tilt && a.blink === b.blink && a.yawn === b.yawn && a.hovered === b.hovered
        && a.pleased === b.pleased && a.habit === b.habit && a.side === b.side
}

const DURATION = { glance: 1.2, stretch: 1.3, yawn: 1.9, fidget: 0.6 }
const MARKS = { glance: [], stretch: [0.6], yawn: [0.25, 1.5], fidget: [0.15, 0.3, 0.45], habit: [] }

function duration(action) {
    if (action.kind === "habit") return action.habit === "wingStretch" || action.habit === "scarfTug" ? 1.2 : 0.6
    return DURATION[action.kind]
}

// Tenths, so small cursor moves don't redraw the face.
const quantized = v => ({ dx: Math.round(v.dx * 10) / 10, dy: Math.round(v.dy * 10) / 10 })

// Eyes point toward the cursor and reach the edge of the eye once it's 160 pt away, in 16 directions and quarter
// reaches, so a cursor moving about turns his eyes a few times rather than on every poll.
export function gazeToward(cursor) {
    const distance = Math.hypot(cursor.x, cursor.y)
    if (distance <= 1) return { dx: 0, dy: 0 }
    const reach = Math.max(0.25, Math.round(Math.min(1, distance / 160) * 4) / 4)
    const step = Math.PI / 8
    const angle = Math.round(Math.atan2(-cursor.y, cursor.x) / step) * step
    return quantized({ dx: Math.cos(angle) * reach, dy: Math.sin(angle) * reach })
}

function bounceFor(from, to, now) {
    switch (to) {
    case "listening": case "dictating": return [{ squash: -0.06, until: now + 0.08 }, { squash: 0.08, until: now + 0.24 }]
    case "speaking": return [{ squash: 0.05, until: now + 0.16 }]
    case "thinking": case "transcribing": return [{ squash: -0.05, until: now + 0.16 }]
    default: return from === "idle" ? [] : [{ squash: -0.07, until: now + 0.2 }]
    }
}

export class Life {
    constructor(seed, now) {
        now = now || 0
        this.rng = new SeededRandom(seed)
        this.last = { state: "idle", asleep: false, late: false, cursor: null, towardCentre: -1 }
        this.started = false
        this.nextBlink = now + 3
        this.blinkEnd = 0
        this.secondBlink = null
        this.bounce = []
        this.pleasedUntil = 0
        this.hovered = false
        this.lastCursor = null
        this.cursorMovedAt = -Infinity
        this.action = null
        this.actionStart = 0
        this.nextAction = now + 4
        // Speaking: alternates between the bubble and the user. Thinking: between left and right.
        this.lookAway = true
        this.lookSwitch = 0
        // When the pose next changes without new input; Infinity while nothing is scheduled.
        this.wake = Infinity
    }

    update(input, now) {
        this.react(input, now)
        this.advance(input, now)
        this.last = input
        this.started = true
        const pose = this.pose(input, now)
        this.wake = this.nextWake(input, now)
        return pose
    }

    react(input, now) {
        const rng = this.rng
        if (this.started && input.state !== this.last.state) {
            this.bounce = bounceFor(this.last.state, input.state, now)
            this.action = null
            this.nextAction = now + rng.between(2, 5)
            this.lookSwitch = now
            this.lookAway = false
            this.blink(now)
        }
        if (this.started && input.asleep !== this.last.asleep) {
            if (input.asleep) {
                this.start({ kind: "yawn" }, now)
            } else {
                this.action = null
                this.bounce = [{ squash: 0.07, until: now + 0.18 }]
                this.nextAction = now + rng.between(3, 6)
            }
        }
        const c = input.cursor
        const over = !!c && c.x >= BODY.x && c.x <= BODY.x + BODY.width && c.y >= BODY.y && c.y <= BODY.y + BODY.height
        if (over && !this.hovered) {
            this.bounce = [{ squash: -0.09, until: now + 0.1 }, { squash: 0.07, until: now + 0.26 }]
            if (!input.asleep) this.pleasedUntil = now + 1.2
            if (this.action && this.action.kind === "glance") this.action = null
        }
        this.hovered = over
        if (c) {
            const p = this.lastCursor
            if (p && Math.hypot(c.x - p.x, c.y - p.y) > 4) this.cursorMovedAt = now
            this.lastCursor = c
        } else {
            this.lastCursor = null
        }
    }

    advance(input, now) {
        const rng = this.rng
        this.bounce = this.bounce.filter(b => b.until > now)
        if (input.asleep) {
            this.blinkEnd = 0
            this.secondBlink = null
        } else if (this.secondBlink !== null && now >= this.secondBlink) {
            this.secondBlink = null
            this.blinkEnd = now + 0.12
        } else if (now >= this.nextBlink) {
            this.blink(now)
            if (rng.chance(0.15)) this.secondBlink = now + 0.3
        }
        if (this.action && now >= this.actionStart + duration(this.action)) {
            this.action = null
            this.nextAction = now + rng.between(5, 12)
        }
        if (this.action || input.state !== "idle" || input.asleep || now < this.nextAction) return
        if (this.hovered || this.following(now)) {
            this.nextAction = now + rng.between(1, 2.5)
            return
        }
        this.start(this.pickAction(input.late), now)
    }

    blink(now) {
        this.blinkEnd = now + 0.12
        this.nextBlink = now + this.rng.between(2.5, 6)
    }

    start(action, now) {
        this.action = action
        this.actionStart = now
    }

    pickAction(late) {
        const rng = this.rng
        const roll = rng.next()
        const yawn = late ? 0.25 : 0.03
        if (roll < yawn) return { kind: "yawn" }
        if (roll < yawn + 0.08) return { kind: "stretch" }
        if (roll < yawn + 0.14) return { kind: "fidget" }
        if (roll < yawn + 0.24) return { kind: "habit", habit: "bob" }
        if (roll < yawn + 0.32) return { kind: "habit", habit: "tailFlick" }
        if (roll < yawn + 0.37) return { kind: "habit", habit: "scarfTug" }
        if (roll < yawn + 0.42) return { kind: "habit", habit: "ruffle" }
        if (roll < yawn + 0.47) return { kind: "habit", habit: "wingStretch" }
        const angle = rng.between(0, 2 * Math.PI)
        const reach = rng.between(0.5, 1)
        return { kind: "glance", gaze: quantized({ dx: Math.cos(angle) * reach, dy: Math.sin(angle) * reach * 0.6 }) }
    }

    following(now) { return this.lastCursor !== null && now - this.cursorMovedAt < ATTENTION }

    pose(input, now) {
        const rng = this.rng
        const pose = restPose()
        pose.hovered = this.hovered
        pose.pleased = this.hovered && now < this.pleasedUntil
        pose.blink = now < this.blinkEnd
        pose.squash = this.bounce.length ? this.bounce[0].squash : 0
        const side = input.towardCentre
        pose.side = side

        switch (input.state) {
        case "listening":
            pose.gaze = { dx: 0.15 * side, dy: -0.1 }
            pose.lean = side
            pose.tilt = 4 * side
            break
        case "thinking": case "transcribing":
            if (now >= this.lookSwitch) {
                this.lookAway = !this.lookAway
                this.lookSwitch = now + rng.between(1.2, 2.6)
            }
            pose.gaze = { dx: this.lookAway ? 0.7 : -0.7, dy: -0.75 }
            break
        case "speaking":
            if (now >= this.lookSwitch) {
                this.lookAway = !this.lookAway
                this.lookSwitch = now + (this.lookAway ? rng.between(1.6, 3) : rng.between(0.8, 1.6))
            }
            pose.gaze = this.lookAway ? { dx: 0.3 * side, dy: -0.8 } : { dx: 0, dy: 0 }
            break
        default:
            if ((this.hovered || this.following(now)) && input.cursor) pose.gaze = gazeToward(input.cursor)
        }

        if (input.asleep) {
            pose.gaze = { dx: 0, dy: 0 }
            pose.blink = false
        }
        const action = this.action
        if (action) {
            const t = now - this.actionStart
            switch (action.kind) {
            case "glance": pose.gaze = action.gaze; break
            case "stretch": if (t < 0.6 && pose.squash === 0) pose.squash = 0.08; break
            case "yawn":
                pose.yawn = t >= 0.25 && t < 1.5
                if (pose.yawn) {
                    pose.tilt = -5 * side
                    if (pose.squash === 0) pose.squash = 0.04
                }
                break
            case "fidget": pose.tilt = [6, -5, 3, 0][Math.min(3, Math.floor(t / 0.15))]; break
            case "habit": pose.habit = action.habit; break
            }
        }
        return pose
    }

    nextWake(input, now) {
        const times = this.bounce.map(b => b.until)
        if (!input.asleep) {
            times.push(this.nextBlink)
            if (this.blinkEnd > now) times.push(this.blinkEnd)
            if (this.secondBlink !== null) times.push(this.secondBlink)
        }
        if (this.pleasedUntil > now) times.push(this.pleasedUntil)
        if (this.lastCursor !== null && this.cursorMovedAt + ATTENTION > now) times.push(this.cursorMovedAt + ATTENTION)
        if (this.action) {
            for (const m of MARKS[this.action.kind]) times.push(this.actionStart + m)
            times.push(this.actionStart + duration(this.action))
        } else if (input.state === "idle" && !input.asleep) {
            times.push(this.nextAction)
        }
        if (["speaking", "thinking", "transcribing"].includes(input.state)) times.push(this.lookSwitch)
        const due = times.filter(t => t > now)
        return due.length ? Math.min.apply(null, due) : Infinity
    }
}
