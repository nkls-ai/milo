// Milo's moves (WrenMotion.swift's WrenClip and WrenDirector.swift's WrenClips): short authored curves laid over the
// springs, a hop, a nod, a tail tick. Each track is keys of [seconds, offset], starting and ending at zero so a clip
// never pops in or out. Mode "add" lays it on the pose after the springs (exact timing); "target" adds it to where
// the springs head, so they soften it and overshoot (slow weight shifts).

function clip(name, tracks, mode = "add") {
    let duration = 0
    for (const keys of Object.values(tracks)) duration = Math.max(duration, keys[keys.length - 1][0])
    return { name, mode, tracks, duration }
}

// The offset on `channel` at `t` seconds in: a Catmull-Rom spline through the keys, at rest on the first and last.
export function value(c, channel, t) {
    const keys = c.tracks[channel]
    if (!keys || keys.length === 0) return 0
    if (t <= keys[0][0]) return keys[0][1]
    const last = keys[keys.length - 1]
    if (t >= last[0]) return last[1]
    const i = keys.findIndex(k => k[0] > t) - 1
    const a = keys[i], b = keys[i + 1]
    const span = b[0] - a[0]
    if (span <= 0) return b[1]
    const u = (t - a[0]) / span
    const slope = j => {
        if (j <= 0 || j >= keys.length - 1) return 0
        return (keys[j + 1][1] - keys[j - 1][1]) / (keys[j + 1][0] - keys[j - 1][0]) * span
    }
    const m0 = slope(i), m1 = slope(i + 1)
    const u2 = u * u, u3 = u2 * u
    return (2 * u3 - 3 * u2 + 1) * a[1] + (u3 - 2 * u2 + u) * m0 + (-2 * u3 + 3 * u2) * b[1] + (u3 - u2) * m1
}

const HORIZONTAL = ["lean", "headTilt", "headX", "gazeX", "turn", "scarf", "crestSway"]

// The same move facing the other way: horizontal channels change sign.
export function mirrored(c, side) {
    if (side >= 0) return c
    const tracks = Object.assign({}, c.tracks)
    for (const ch of HORIZONTAL) if (tracks[ch]) tracks[ch] = tracks[ch].map(k => [k[0], -k[1]])
    return clip(c.name, tracks, c.mode)
}

function both(l, r, keys) {
    const tracks = {}
    tracks[l] = keys
    tracks[r] = keys
    return tracks
}
const wings = keys => both("wingL", "wingR", keys)
const tracks = (...parts) => Object.assign({}, ...parts)

// A hop for joy: crouch (anticipation), spring up with the wings lifting, land in a squash, settle.
export const hop = clip("hop", tracks({
    squash: [[0, 0], [0.09, -0.15], [0.17, 0.13], [0.3, 0.03], [0.39, -0.11], [0.5, 0.035], [0.64, 0]],
    lift: [[0, 0], [0.1, 0], [0.25, 17], [0.38, 0], [0.64, 0]],
    headY: [[0, 0], [0.1, 2], [0.2, -2], [0.4, 2], [0.6, 0]],
}, wings([[0, 0], [0.12, -3], [0.22, 26], [0.36, -5], [0.52, 0]])))

// Quietly proud of a job done: chest out, a slow nod, eyes narrowed in a pleased squint.
export const proud = clip("proud", tracks({
    squash: [[0, 0], [0.25, 0.06], [0.9, 0.04], [1.3, 0]],
    headY: [[0, 0], [0.2, -2], [0.45, 3.5], [0.75, -0.5], [1, 0]],
    tail: [[0, 0], [0.3, 12], [1, 8], [1.4, 0]],
}, both("lidL", "lidR", [[0, 0], [0.35, 0.25], [1.1, 0.25], [1.4, 0]])))

// A small nod while you talk to him: "mm-hm".
export const nod = clip("nod", {
    headY: [[0, 0], [0.1, 3], [0.26, -0.6], [0.4, 0]],
    squash: [[0, 0], [0.1, -0.02], [0.3, 0]],
    headTilt: [[0, 0], [0.12, 1.5], [0.4, 0]],
})

// "Yes?": a two-beat tail tick while a question waits.
export const tailTick = clip("tailTick", {
    tail: [[0, 0], [0.07, 18], [0.16, -4], [0.24, 14], [0.34, -2], [0.5, 0]],
    tailFan: [[0, 0], [0.08, 0.5], [0.5, 0]],
})

export const tailFlick = clip("tailFlick", {
    tail: [[0, 0], [0.06, 22], [0.2, -6], [0.4, 0]],
    tailFan: [[0, 0], [0.06, 0.6], [0.3, 0]],
})

// The wren bob: two quick knee-dips with the tail flicking up against them.
export const bob = clip("bob", {
    squash: [[0, 0], [0.07, -0.07], [0.16, 0.03], [0.26, -0.05], [0.36, 0.015], [0.48, 0]],
    headY: [[0, 0], [0.08, 2], [0.18, -1], [0.28, 1.5], [0.48, 0]],
    tail: [[0, 0], [0.08, 12], [0.2, -3], [0.3, 8], [0.5, 0]],
})

// Pulling back from bad news: a quick flinch away, eyes wide, wings in.
export const flinch = clip("flinch", tracks({
    lean: [[0, 0], [0.06, -5], [0.45, 0]],
    squash: [[0, 0], [0.05, -0.08], [0.15, 0.04], [0.32, 0]],
    headY: [[0, 0], [0.05, -2], [0.3, 0]],
}, both("eyeL", "eyeR", [[0, 0], [0.05, 0.15], [0.45, 0]]), wings([[0, 0], [0.05, 10], [0.3, 0]])))

// Ears up: a small anticipation dip, then up and alert.
export const perk = clip("perk", tracks({
    squash: [[0, 0], [0.06, -0.06], [0.16, 0.07], [0.32, 0]],
    lift: [[0, 0], [0.08, 0], [0.16, 4], [0.32, 0]],
}, both("browL", "browR", [[0, 0], [0.1, 0.4], [0.4, 0]]), both("eyeL", "eyeR", [[0, 0], [0.1, 0.1], [0.35, 0]])))

// A breath in before speaking.
export const inhale = clip("inhale", {
    squash: [[0, 0], [0.15, 0.05], [0.32, 0]],
    headY: [[0, 0], [0.15, -1.5], [0.32, 0]],
})

// A breath out: sinking back after speaking, or into sleep.
export const settle = clip("settle", {
    squash: [[0, 0], [0.12, -0.05], [0.35, 0.012], [0.55, 0]],
    headY: [[0, 0], [0.15, 1.5], [0.5, 0]],
})

// Thinking starts: the head goes back a little and over.
export const hmm = clip("hmm", {
    headTilt: [[0, 0], [0.2, -5], [0.6, 0]],
    headY: [[0, 0], [0.15, -1.5], [0.5, 0]],
    lean: [[0, 0], [0.2, -1.5], [0.6, 0]],
})

// Taps his tail while he thinks, like drumming fingers.
export const tap = clip("tap", { tail: [[0, 0], [0.08, 9], [0.2, 0], [0.28, 6], [0.4, 0]] })

// A beat of speech: a nod and the brows lifting with it.
export const emphasis = clip("emphasis", tracks({
    headY: [[0, 0], [0.08, -1.5], [0.2, 2], [0.4, 0]],
    squash: [[0, 0], [0.1, 0.02], [0.3, 0]],
}, both("browL", "browR", [[0, 0], [0.1, 0.35], [0.45, 0]])))

// Talking with his near wing, like a hand.
export function gesture(side) {
    const near = side < 0 ? "R" : "L"
    const t = {}
    t["wing" + near] = [[0, 0], [0.18, 22], [0.4, 14], [0.6, 18], [0.85, 0]]
    t["open" + near] = [[0, 0], [0.18, 0.7], [0.6, 0.65], [0.85, 0]]
    return clip("gesture", t)
}

// Pleased: a little side-to-side wiggle after the hop lands, the tuft swinging after it.
export const wiggle = clip("wiggle", tracks({
    lean: [[0, 0], [0.42, 0], [0.52, 5], [0.66, -5], [0.8, 3.5], [0.94, -2], [1.1, 0]],
}, both("lowerL", "lowerR", [[0, 0], [0.45, 0.25], [0.95, 0.25], [1.15, 0]])))

// Surprised: he fluffs up, rounder for a moment, tuft up and eyes wide, then settles.
export const fluffUp = clip("fluffUp", tracks({
    squash: [[0, 0], [0.07, -0.08], [0.24, 0.03], [0.45, 0]],
    crest: [[0, 0], [0.12, 0.6], [0.5, 0.4], [0.9, 0]],
}, both("eyeL", "eyeR", [[0, 0], [0.07, 0.12], [0.5, 0]])))

// Wings spread and flutter twice.
export const flutter = clip("flutter", tracks(
    both("openL", "openR", [[0, 0], [0.1, 1], [0.6, 1], [0.8, 0]]),
    wings([[0, 0], [0.15, 32], [0.25, 4], [0.35, 32], [0.45, 4], [0.55, 24], [0.75, 0]])))

export const deflate = clip("deflate", {
    squash: [[0, 0], [0.3, -0.05], [0.9, 0]],
    headY: [[0, 0], [0.3, 2], [1, 0]],
}, "target")

// Confused: the head swings one way, then the other, and comes to rest tilted.
export const doubleTake = clip("doubleTake", {
    headTilt: [[0, 0], [0.1, 8], [0.28, -12], [0.5, 0]],
    headX: [[0, 0], [0.1, 2], [0.28, -1.5], [0.45, 0]],
    gazeX: [[0, 0], [0.08, 0.5], [0.26, -0.4], [0.45, 0]],
})

// Shakes himself awake (or just smooths his feathers): a fast wobble that dies out.
export const ruffle = clip("ruffle", tracks({
    headX: [[0, 0], [0.06, -2], [0.12, 2], [0.18, -1.5], [0.24, 1], [0.32, 0]],
    headTilt: [[0, 0], [0.06, -4], [0.12, 4], [0.18, -3], [0.26, 2], [0.36, 0]],
    squash: [[0, 0], [0.05, 0.06], [0.12, -0.04], [0.2, 0.03], [0.36, 0]],
    tail: [[0, 0], [0.08, 10], [0.16, -6], [0.24, 4], [0.4, 0]],
}, wings([[0, 0], [0.06, 8], [0.12, -2], [0.18, 6], [0.3, 0]]),
   both("lidL", "lidR", [[0, 0], [0.08, 0.5], [0.3, 0.4], [0.45, 0]])))

// Rolling up his sleeves: tosses the scarf back with a determined little nod.
export const rollUp = clip("rollUp", {
    squash: [[0, 0], [0.08, -0.06], [0.2, 0.05], [0.36, 0]],
    headY: [[0, 0], [0.12, -1.5], [0.26, 2.5], [0.45, 0]],
    scarf: [[0, 0], [0.1, 12], [0.3, 0]],
})

// Crouch, then spring into the air with the wings coming up.
export const takeoff = clip("takeoff", tracks({
    squash: [[0, 0], [0.1, -0.15], [0.2, 0.15], [0.4, 0]],
    lift: [[0, 0], [0.12, -1], [0.22, 10], [0.42, 0]],
    tail: [[0, 0], [0.1, -10], [0.25, 10], [0.4, 0]],
}, wings([[0, 0], [0.1, -10], [0.2, 30], [0.35, 0]])))

// Keeps him on the ground through the crouch: the wings only come up as he springs.
export const holdOff = clip("holdOff", { fly: [[0, -1], [0.12, -1], [0.18, 0]] }, "target")

// Touchdown: a squash on landing, wings out for balance, the tail bouncing.
export const land = clip("land", tracks({
    squash: [[0, 0], [0.06, -0.16], [0.18, 0.06], [0.3, -0.03], [0.46, 0]],
    tail: [[0, 0], [0.08, -12], [0.25, 9], [0.46, 0]],
    headY: [[0, 0], [0.06, 3], [0.2, -1], [0.36, 0]],
}, wings([[0, 0], [0.06, 22], [0.25, -4], [0.42, 0]])))

// A wing reaches over and tugs the scarf straight.
export function scarfTug(side) {
    const t = {
        scarf: [[0, 0], [0.36, 0], [0.44, -14], [0.62, 6], [0.95, 0]],
        headY: [[0, 0], [0.3, 1.5], [0.7, 1.5], [0.95, 0]],
        gazeY: [[0, 0], [0.15, 0.55], [0.75, 0.5], [0.95, 0]],
        gazeX: [[0, 0], [0.15, 0.35 * -side], [0.75, 0.3 * -side], [0.95, 0]],
    }
    t[side < 0 ? "wingR" : "wingL"] = [[0, 0], [0.22, -62], [0.38, -58], [0.48, -64], [0.85, 0]]
    return clip("scarfTug", t)
}

// One wing stretched out long and folded again, eyes half shut with the pleasure of it.
export function wingStretch(side) {
    const near = side < 0 ? "R" : "L"
    const t = tracks({
        lean: [[0, 0], [0.3, 2 * side], [1.2, 0]],
        squash: [[0, 0], [0.3, 0.04], [1, 0.02], [1.2, 0]],
    }, both("lidL", "lidR", [[0, 0], [0.3, 0.3], [0.95, 0.3], [1.2, 0]]))
    t["wing" + near] = [[0, 0], [0.3, -12], [0.9, -6], [1.2, 0]]
    t["open" + near] = [[0, 0], [0.3, 1], [0.9, 1], [1.2, 0]]
    return clip("wingStretch", t)
}

// A line of notes: the pencil runs along the pad in small strokes, the head nodding along (never sideways, which
// would set the scarf swinging between lines).
export const scribble = clip("scribble", {
    pen: [[0, 0], [0.12, -0.7], [0.24, -0.25], [0.36, -0.5], [0.48, 0.05], [0.6, -0.15], [0.72, 0.45],
          [0.84, 0.2], [0.96, 0.75], [1.2, 0]],
    headY: [[0, 0], [0.12, 0.6], [0.48, 0.3], [0.84, 0.6], [1.2, 0]],
})

// Looks up from the notepad to listen, the tuft lifting, then back down to write it.
export const glanceUp = clip("glanceUp", tracks({
    gazeY: [[0, 0], [0.12, -0.8], [1.1, -0.75], [1.3, 0]],
    gazeX: [[0, 0], [0.12, -0.3], [1.1, -0.3], [1.3, 0]],
    headY: [[0, 0], [0.14, -2.2], [1.1, -2], [1.35, 0]],
    headTilt: [[0, 0], [0.2, -5], [1.0, -4], [1.4, 0]],
    crest: [[0, 0], [0.15, 0.35], [1.1, 0.3], [1.4, 0]],
}, both("browL", "browR", [[0, 0], [0.14, 0.3], [1.1, 0.25], [1.35, 0]]),
   both("lidL", "lidR", [[0, 0], [0.12, -0.18], [1.1, -0.18], [1.3, 0]])))
