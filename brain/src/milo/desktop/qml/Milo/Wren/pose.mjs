// Every number Milo's rig reads (MiloKit/Views/Wren/WrenPose.swift). A state is a set of these numbers, and a change
// of state is the springs moving from one set to the next, so nothing ever pops.
//
// Figure space is the design page's: a 200-unit box with the ground at y = 182 and his middle at x = 100, y down.

// name: [rest, spring response (s), damping, epsilon]. Body parts are slower and heavier than eyes; the tail, scarf
// and head are loose so they lag the body (overlapping action).
const SPEC = {
    turn: [-0.2, 0.45, 0.85, 0.002],       // -1...1, negative faces the viewer's left
    lean: [0, 0.42, 0.6, 0.05],            // degrees clockwise, about his feet
    squash: [0, 0.2, 0.42, 0.002],         // positive is taller and thinner; squash and stretch overshoots
    lift: [0, 0.26, 0.6, 0.02],            // figure units off the ground
    headTilt: [0, 0.5, 0.48, 0.05],        // the head lags the body and settles after it
    headX: [0, 0.32, 0.55, 0.02],
    headY: [0, 0.32, 0.55, 0.02],
    gazeX: [0, 0.09, 0.92, 0.002],         // saccades: fast and clean
    gazeY: [0, 0.09, 0.92, 0.002],
    lidL: [0.2, 0.12, 0.9, 0.002],         // 0 open ... 1 shut; about 0.2 at rest
    lidR: [0.2, 0.12, 0.9, 0.002],
    lowerL: [0.14, 0.12, 0.9, 0.002],      // lower lids pushing up into a smile
    lowerR: [0.14, 0.12, 0.9, 0.002],
    eyeL: [1, 0.18, 0.7, 0.002],
    eyeR: [1, 0.18, 0.7, 0.002],
    browL: [0, 0.2, 0.62, 0.002],          // raised (+) or lowered
    browR: [0, 0.2, 0.62, 0.002],
    browTiltL: [0, 0.2, 0.62, 0.002],      // + lifts the inner end (worried)
    browTiltR: [0, 0.2, 0.62, 0.002],
    beak: [0, 0.1, 0.7, 0.002],            // follows the voice: quick, but never a snap
    blush: [0.3, 0.6, 1, 0.002],
    wingL: [0, 0.26, 0.5, 0.05],           // degrees, positive raises the wing away from the body
    wingR: [0, 0.26, 0.5, 0.05],
    openL: [0, 0.24, 0.8, 0.002],          // 0 folded ... 1 spread like a hand
    openR: [0, 0.24, 0.8, 0.002],
    fly: [0, 0.32, 0.85, 0.002],           // 0 perched ... 1 in the air
    tail: [0, 0.38, 0.32, 0.05],           // springy: the mood-tail wags into place
    tailFan: [0, 0.3, 0.6, 0.002],
    scarf: [0, 0.75, 0.22, 0.05],          // a loose knitted end, swinging; driven by motion, never by a state
    scarfToss: [0, 0.36, 0.55, 0.002],     // 0 hanging ... 1 tossed over his shoulder
    scarfUp: [0, 0.6, 0.9, 0.002],         // 0 round his neck ... 1 pulled over his beak, for sleeping
    feet: [1, 0.2, 1, 0.002],
    crest: [0, 0.26, 0.5, 0.002],          // the tuft: -1 laid flat, 1 perked right up, with a little bounce
    crestSway: [0, 0.4, 0.28, 0.05],       // soft feathers wobble after every move
    breath: [0, 0.2, 1, 0.002],            // breathing -1...1, for stills; live, the view breathes him
    pad: [0, 0.36, 0.72, 0.002],           // 0 no notepad ... 1 held up, for meeting notes
    pen: [0, 0.1, 0.75, 0.002],            // the pencil along the notepad's line, -1...1
}

export const CHANNELS = Object.keys(SPEC)

export function rest() {
    const pose = {}
    for (const name of CHANNELS) pose[name] = SPEC[name][0]
    return pose
}

export function copy(pose) { return Object.assign({}, pose) }

export const response = name => SPEC[name][1]
export const damping = name => SPEC[name][2]
export const epsilon = name => SPEC[name][3]

export function smooth(a, b, x) {
    const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
