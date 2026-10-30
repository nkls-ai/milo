// The one place that decides how Milo looks and moves. Everything else on the site talks to Milo in
// named poses and moves, and the rig turns a pose (a handful of numbers) into an SVG. To try another
// design, write a rig with the same shape as `rig` below and change the import.
//
// The wren is the app's: wren.js is a port of app/Sources/MiloKit/Views/Wren/WrenRig.swift, the poses
// come from WrenDirector.swift and the moves from WrenClips (WrenDirector.swift and WrenMotion.swift).
// He sits facing a little left, toward the page, so "near" is his right wing.
import * as wren from './wren.js';
import { pose as mergePose } from './lib.js';

/** The numbers that move, each on its own spring. */
const channels = Object.keys(wren.springs);

/**
 * Named poses, as the director sets them for each state (with level at about 0.4 where a state follows
 * a voice), plus a few the site needs. Everything left out stays at rest.
 */
const poses = {
  idle: {},
  listening: { lean: -4, lid: 0.06, eye: 1.06, brow: 0.35, tail: 18, tailFan: 0.4, crest: 0.8, squash: 0.02 },
  thinking: {
    gazeX: -0.5, gazeY: -0.6, lidL: 0.28, lidR: 0.24, browL: 0.75, browR: -0.1, browTiltR: -0.3,
    headTilt: 3, tail: 4, crest: 0.25,
  },
  speaking: { beak: 0.3, brow: 0.3, headY: -0.8, lid: 0.14, squash: -0.01, tail: 6, crest: 0.27 },
  working: { lid: 0.3, brow: -0.15, browTilt: -0.25, scarfToss: 1, tail: 4, crest: 0.2 },
  // working, looking down at what he works on, the scarf already over his shoulder
  busy: { turn: -0.35, gazeX: -0.5, gazeY: 0.7, lid: 0.3, brow: -0.15, browTilt: -0.25, scarfToss: 1, tail: 4, crest: 0.2 },
  flying: { turn: -0.3, fly: 1, feet: 0, wing: 40, lid: 0.08, brow: 0.3, tail: 0, tailFan: 1, crest: -0.4, lean: -6, gazeX: -0.5 },
  pointing: { gazeX: -0.85, gazeY: -0.5, headX: -1.7, headY: -1, lean: -3.4, wingL: 30, openL: 1, brow: 0.3 },
  happy: { lower: 1, lid: 0.2, blush: 0.8, tail: 12, crest: 0.4, brow: 0.35, squash: 0.02 },
  // surprised and glad: tuft high, eyes wide, brows up, beak open a little, tail fanned
  excited: { lid: 0, eye: 1.12, beak: 0.3, blush: 0.75, tail: 20, tailFan: 0.7, crest: 1, brow: 0.6, wing: 12 },
  concerned: { browTilt: 1, brow: 0.1, lid: 0.3, tail: -8, crest: -0.3, wing: -4, lean: 2, squash: -0.02, headTilt: 0 },
  // asleep: eyes closed, tuft flat, tucked a little into his scarf
  sleepy: {
    lid: 1, lower: 0, scarfUp: 1, headY: 2.5, headTilt: -5, squash: -0.06, tail: -12, crest: -1,
    brow: -0.1, wing: -3,
  },
  confused: {
    headTilt: 7, browR: 0.7, browL: -0.25, browTiltL: -0.3, lidL: 0.3, lidR: 0.12, gazeX: 0.3, crest: 0.4,
  },
  // quietly pleased with a job done: a squint of a smile, chest out, tail up
  proud: { lower: 1, lid: 0.2, brow: 0.4, headTilt: 3, tail: 18, tailFan: 0.6, squash: 0.03, blush: 0.5, crest: 0.45, gazeY: -0.2 },
  // waiting for a yes: head tilted, eyes wide on you, tuft up
  waiting: { headTilt: -12, lid: 0.05, eye: 1.08, brow: 0.45, browTilt: 0.2, tail: 16, tailFan: 0.4, crest: 0.5 },
};

/** Clip tracks as [seconds, offset] keys. Each starts and ends at zero, so a move never pops. */
const clip = (tracks, mode = 'add') => ({ mode, tracks, duration: Math.max(...Object.values(tracks).map((k) => k[k.length - 1][0])) });
/** The same move facing the other way: the app mirrors some moves toward the side he faces. */
const mirrored = (c) => {
  const tracks = { ...c.tracks };
  for (const k of ['lean', 'headTilt', 'headX', 'gazeX', 'turn', 'scarf', 'crestSway']) {
    if (tracks[k]) tracks[k] = tracks[k].map(([t, v]) => [t, -v]);
  }
  return { ...c, tracks };
};

/** Moves: offsets laid over his pose for a moment. `add` lands exactly; `target` goes through the springs. */
const gestures = {
  // a hop for joy: crouch, spring up with the wings lifting, land in a squash, settle
  hop: clip({
    squash: [[0, 0], [0.09, -0.15], [0.17, 0.13], [0.3, 0.03], [0.39, -0.11], [0.5, 0.035], [0.64, 0]],
    lift: [[0, 0], [0.1, 0], [0.25, 17], [0.38, 0], [0.64, 0]],
    wingL: [[0, 0], [0.12, -3], [0.22, 26], [0.36, -5], [0.52, 0]],
    wingR: [[0, 0], [0.12, -3], [0.22, 26], [0.36, -5], [0.52, 0]],
    headY: [[0, 0], [0.1, 2], [0.2, -2], [0.4, 2], [0.6, 0]],
  }),
  // pleased: a little side-to-side wiggle after the hop lands, the tuft swinging after it
  wiggle: clip({
    lean: [[0, 0], [0.42, 0], [0.52, 5], [0.66, -5], [0.8, 3.5], [0.94, -2], [1.1, 0]],
    lowerL: [[0, 0], [0.45, 0.25], [0.95, 0.25], [1.15, 0]],
    lowerR: [[0, 0], [0.45, 0.25], [0.95, 0.25], [1.15, 0]],
  }),
  // surprised: he fluffs up, rounder for a moment, tuft up and eyes wide, then settles
  fluff: clip({
    squash: [[0, 0], [0.07, -0.08], [0.24, 0.03], [0.45, 0]],
    crest: [[0, 0], [0.12, 0.6], [0.5, 0.4], [0.9, 0]],
    eyeL: [[0, 0], [0.07, 0.12], [0.5, 0]],
    eyeR: [[0, 0], [0.07, 0.12], [0.5, 0]],
  }),
  // quietly proud: chest out, a slow nod, eyes narrowed
  proud: clip({
    squash: [[0, 0], [0.25, 0.06], [0.9, 0.04], [1.3, 0]],
    headY: [[0, 0], [0.2, -2], [0.45, 3.5], [0.75, -0.5], [1, 0]],
    lidL: [[0, 0], [0.35, 0.25], [1.1, 0.25], [1.4, 0]],
    lidR: [[0, 0], [0.35, 0.25], [1.1, 0.25], [1.4, 0]],
    tail: [[0, 0], [0.3, 12], [1, 8], [1.4, 0]],
  }),
  // "mm-hm", as your words arrive
  nod: clip({
    headY: [[0, 0], [0.1, 3], [0.26, -0.6], [0.4, 0]],
    squash: [[0, 0], [0.1, -0.02], [0.3, 0]],
    headTilt: [[0, 0], [0.12, 1.5], [0.4, 0]],
  }),
  // "yes?": a two-beat tail tick while a question waits
  tick: clip({
    tail: [[0, 0], [0.07, 18], [0.16, -4], [0.24, 14], [0.34, -2], [0.5, 0]],
    tailFan: [[0, 0], [0.08, 0.5], [0.5, 0]],
  }),
  tailFlick: clip({
    tail: [[0, 0], [0.06, 22], [0.2, -6], [0.4, 0]],
    tailFan: [[0, 0], [0.06, 0.6], [0.3, 0]],
  }),
  // the wren bob: two quick knee-dips with the tail flicking up against them
  bob: clip({
    squash: [[0, 0], [0.07, -0.07], [0.16, 0.03], [0.26, -0.05], [0.36, 0.015], [0.48, 0]],
    headY: [[0, 0], [0.08, 2], [0.18, -1], [0.28, 1.5], [0.48, 0]],
    tail: [[0, 0], [0.08, 12], [0.2, -3], [0.3, 8], [0.5, 0]],
  }),
  // pulling back from bad news: a quick flinch, eyes wide, wings in
  flinch: clip({
    lean: [[0, 0], [0.06, -5], [0.45, 0]],
    squash: [[0, 0], [0.05, -0.08], [0.15, 0.04], [0.32, 0]],
    eyeL: [[0, 0], [0.05, 0.15], [0.45, 0]],
    eyeR: [[0, 0], [0.05, 0.15], [0.45, 0]],
    wingL: [[0, 0], [0.05, 10], [0.3, 0]],
    wingR: [[0, 0], [0.05, 10], [0.3, 0]],
    headY: [[0, 0], [0.05, -2], [0.3, 0]],
  }),
  // ears up: a small dip, then up and alert, tuft and all
  perk: clip({
    squash: [[0, 0], [0.06, -0.06], [0.16, 0.07], [0.32, 0]],
    lift: [[0, 0], [0.08, 0], [0.16, 4], [0.32, 0]],
    browL: [[0, 0], [0.1, 0.4], [0.4, 0]],
    browR: [[0, 0], [0.1, 0.4], [0.4, 0]],
    eyeL: [[0, 0], [0.1, 0.1], [0.35, 0]],
    eyeR: [[0, 0], [0.1, 0.1], [0.35, 0]],
  }),
  // a breath in before speaking, and out after
  inhale: clip({
    squash: [[0, 0], [0.15, 0.05], [0.32, 0]],
    headY: [[0, 0], [0.15, -1.5], [0.32, 0]],
  }),
  settle: clip({
    squash: [[0, 0], [0.12, -0.05], [0.35, 0.012], [0.55, 0]],
    headY: [[0, 0], [0.15, 1.5], [0.5, 0]],
  }),
  // thinking starts: the head goes back a little and over
  hmm: mirrored(clip({
    headTilt: [[0, 0], [0.2, -5], [0.6, 0]],
    headY: [[0, 0], [0.15, -1.5], [0.5, 0]],
    lean: [[0, 0], [0.2, -1.5], [0.6, 0]],
  })),
  // a beat of speech: a nod with the brows lifting
  emphasis: clip({
    headY: [[0, 0], [0.08, -1.5], [0.2, 2], [0.4, 0]],
    browL: [[0, 0], [0.1, 0.35], [0.45, 0]],
    browR: [[0, 0], [0.1, 0.35], [0.45, 0]],
    squash: [[0, 0], [0.1, 0.02], [0.3, 0]],
  }),
  // talking with his near wing, like a hand
  gesture: clip({
    wingR: [[0, 0], [0.18, 22], [0.4, 14], [0.6, 18], [0.85, 0]],
    openR: [[0, 0], [0.18, 0.7], [0.6, 0.65], [0.85, 0]],
  }),
  // wings spread and flutter twice
  flutter: clip({
    openL: [[0, 0], [0.1, 1], [0.6, 1], [0.8, 0]],
    openR: [[0, 0], [0.1, 1], [0.6, 1], [0.8, 0]],
    wingL: [[0, 0], [0.15, 32], [0.25, 4], [0.35, 32], [0.45, 4], [0.55, 24], [0.75, 0]],
    wingR: [[0, 0], [0.15, 32], [0.25, 4], [0.35, 32], [0.45, 4], [0.55, 24], [0.75, 0]],
  }),
  // confused: the head swings one way, then the other
  doubleTake: clip({
    headTilt: [[0, 0], [0.1, 8], [0.28, -12], [0.5, 0]],
    headX: [[0, 0], [0.1, 2], [0.28, -1.5], [0.45, 0]],
    gazeX: [[0, 0], [0.08, 0.5], [0.26, -0.4], [0.45, 0]],
  }),
  // shakes himself awake, or just smooths his feathers
  ruffle: mirrored(clip({
    headX: [[0, 0], [0.06, -2], [0.12, 2], [0.18, -1.5], [0.24, 1], [0.32, 0]],
    headTilt: [[0, 0], [0.06, -4], [0.12, 4], [0.18, -3], [0.26, 2], [0.36, 0]],
    squash: [[0, 0], [0.05, 0.06], [0.12, -0.04], [0.2, 0.03], [0.36, 0]],
    wingL: [[0, 0], [0.06, 8], [0.12, -2], [0.18, 6], [0.3, 0]],
    wingR: [[0, 0], [0.06, 8], [0.12, -2], [0.18, 6], [0.3, 0]],
    lidL: [[0, 0], [0.08, 0.5], [0.3, 0.4], [0.45, 0]],
    lidR: [[0, 0], [0.08, 0.5], [0.3, 0.4], [0.45, 0]],
    tail: [[0, 0], [0.08, 10], [0.16, -6], [0.24, 4], [0.4, 0]],
  })),
  // "on it": rolls up his sleeves, a determined little nod with the scarf thrown back
  toss: clip({
    squash: [[0, 0], [0.08, -0.06], [0.2, 0.05], [0.36, 0]],
    headY: [[0, 0], [0.12, -1.5], [0.26, 2.5], [0.45, 0]],
    scarf: [[0, 0], [0.1, 12], [0.3, 0]],
  }),
  // a wing reaches over and tugs the scarf straight
  scarfTug: clip({
    scarf: [[0, 0], [0.36, 0], [0.44, -14], [0.62, 6], [0.95, 0]],
    headY: [[0, 0], [0.3, 1.5], [0.7, 1.5], [0.95, 0]],
    gazeY: [[0, 0], [0.15, 0.55], [0.75, 0.5], [0.95, 0]],
    gazeX: [[0, 0], [0.15, 0.35], [0.75, 0.3], [0.95, 0]],
    wingR: [[0, 0], [0.22, -62], [0.38, -58], [0.48, -64], [0.85, 0]],
  }),
  // one wing stretched out long and folded again, eyes half shut with the pleasure of it
  wingStretch: clip({
    lidL: [[0, 0], [0.3, 0.3], [0.95, 0.3], [1.2, 0]],
    lidR: [[0, 0], [0.3, 0.3], [0.95, 0.3], [1.2, 0]],
    lean: [[0, 0], [0.3, -2], [1.2, 0]],
    squash: [[0, 0], [0.3, 0.04], [1, 0.02], [1.2, 0]],
    wingR: [[0, 0], [0.3, -12], [0.9, -6], [1.2, 0]],
    openR: [[0, 0], [0.3, 1], [0.9, 1], [1.2, 0]],
  }),
  // hello: the wing on the open side (his tail is on the other) spread, up, two wags, down
  wave: clip({
    openL: [[0, 0], [0.12, 1], [0.95, 1], [1.15, 0]],
    wingL: [[0, 0], [0.16, 34], [0.34, 64], [0.5, 38], [0.66, 64], [0.85, 36], [1.15, 0]],
    lowerL: [[0, 0], [0.15, 0.76], [0.95, 0.76], [1.15, 0]],
    lowerR: [[0, 0], [0.15, 0.76], [0.95, 0.76], [1.15, 0]],
    browL: [[0, 0], [0.15, 0.45], [1, 0.4], [1.15, 0]],
    browR: [[0, 0], [0.15, 0.45], [1, 0.4], [1.15, 0]],
    headTilt: [[0, 0], [0.2, -4], [0.5, 2], [0.8, -4], [1.15, 0]],
    crest: [[0, 0], [0.15, 0.4], [1, 0.3], [1.15, 0]],
    tail: [[0, 0], [0.15, 12], [1, 10], [1.15, 0]],
  }),
  // the yawn before he falls asleep: beak wide, eyes squeezed, wings lifting
  yawn: clip({
    beak: [[0, 0], [0.35, 1], [0.85, 1], [1.2, 0]],
    lidL: [[0, 0], [0.3, 0.6], [0.9, 0.6], [1.25, 0]],
    lidR: [[0, 0], [0.3, 0.6], [0.9, 0.6], [1.25, 0]],
    lowerL: [[0, 0], [0.3, 0.21], [0.9, 0.21], [1.2, 0]],
    lowerR: [[0, 0], [0.3, 0.21], [0.9, 0.21], [1.2, 0]],
    headTilt: [[0, 0], [0.35, 3], [0.9, 3], [1.25, 0]],
    headY: [[0, 0], [0.35, -3], [0.9, -3], [1.25, 0]],
    squash: [[0, 0], [0.35, 0.05], [0.9, 0.05], [1.25, 0]],
    wingL: [[0, 0], [0.35, 16], [0.9, 16], [1.25, 0]],
    wingR: [[0, 0], [0.35, 16], [0.9, 16], [1.25, 0]],
    browL: [[0, 0], [0.35, 0.3], [0.9, 0.3], [1.25, 0]],
    browR: [[0, 0], [0.35, 0.3], [0.9, 0.3], [1.25, 0]],
  }),
  // crouch, then spring into the air with the wings coming up
  takeoff: clip({
    squash: [[0, 0], [0.1, -0.15], [0.2, 0.15], [0.4, 0]],
    lift: [[0, 0], [0.12, -1], [0.22, 10], [0.42, 0]],
    wingL: [[0, 0], [0.1, -10], [0.2, 30], [0.35, 0]],
    wingR: [[0, 0], [0.1, -10], [0.2, 30], [0.35, 0]],
    tail: [[0, 0], [0.1, -10], [0.25, 10], [0.4, 0]],
  }),
  // keeps him on the ground through the crouch: the wings only come up as he springs
  holdOff: clip({ fly: [[0, -1], [0.12, -1], [0.18, 0]] }, 'target'),
  // touchdown: a squash, wings out for balance, the tail bouncing
  land: clip({
    squash: [[0, 0], [0.06, -0.16], [0.18, 0.06], [0.3, -0.03], [0.46, 0]],
    wingL: [[0, 0], [0.06, 22], [0.25, -4], [0.42, 0]],
    wingR: [[0, 0], [0.06, 22], [0.25, -4], [0.42, 0]],
    tail: [[0, 0], [0.08, -12], [0.25, 9], [0.46, 0]],
    headY: [[0, 0], [0.06, 3], [0.2, -1], [0.36, 0]],
  }),
};

const glad = new Set(['happy', 'excited', 'proud']);
const busy = new Set(['busy', 'working']);
/** The moves a change of pose calls for, as the app's director cues them. */
function cues(a, b) {
  const out = [];
  if (b === 'sleepy') out.push('settle');
  else if (a === 'sleepy') out.push('ruffle');
  if (glad.has(b) && !glad.has(a)) {
    if (b === 'proud' || busy.has(a) || a === 'thinking') out.push('proud');
    else out.push('hop', b === 'excited' ? 'fluff' : 'wiggle');
    if (b === 'excited') out.push('flutter');
  }
  if (b === 'concerned') out.push('flinch');
  if (b === 'confused') out.push('doubleTake', 'fluff');
  if (b === 'listening') out.push('perk');
  if (b === 'speaking') out.push('inhale');
  if (b === 'thinking') out.push('hmm');
  if (b === 'idle' && a === 'speaking') out.push('settle');
  if (b === 'waiting') out.push('tick', 'perk');
  if (busy.has(b) && !busy.has(a)) out.push('toss');
  return out;
}

/** Idle habits and how often he picks each, from CharacterLife.swift; the rest of the time he glances. */
const habits = [[0.24, 'bob'], [0.32, 'tailFlick'], [0.37, 'scarfTug'], [0.42, 'ruffle'], [0.47, 'wingStretch']];

/** Plain-language descriptions, for alt text. */
const describe = {
  idle: 'Milo, a small round lavender wren with a fluffy tuft, soft brows, big dark eyes, pink cheeks and a marigold knitted scarf',
  listening: 'Milo leaning in to listen, his tuft perked up',
  thinking: 'Milo looking up, thinking',
  speaking: 'Milo talking',
  working: 'Milo at work, his scarf tossed over his shoulder',
  busy: 'Milo at work, his scarf tossed over his shoulder',
  flying: 'Milo flying',
  pointing: 'Milo pointing with one wing',
  happy: 'Milo smiling',
  excited: 'Milo fluffed up with delight',
  concerned: 'Milo looking a little worried',
  sleepy: 'Milo asleep, tucked into his scarf with his tuft flat',
  confused: 'Milo tilting his head, confused',
  proud: 'Milo looking quietly pleased',
  waiting: 'Milo waiting for an answer',
};

export const rig = {
  name: 'wren',
  viewBox: '0 0 200 200',
  defaults: wren.defaults,
  channels,
  springs: wren.springs,
  epsilon: wren.epsilon,
  poses,
  gestures,
  cues,
  habits,
  describe: (name) => describe[name] ?? describe.idle,
  /** Fill per-side values (lidL, lidR...) from shared ones, so every number can be animated on its own. */
  resolve: (p) => mergePose(wren.defaults, p),
  /** Where his eyes and head go for a gaze between -1 and 1 on each axis. He turns toward it a little,
   * never so far that his tail swaps sides. */
  gaze: (gx, gy) => ({ gazeX: gx, gazeY: gy, turn: -0.2 + gx * 0.22, headTilt: -3 + gx * 3 }),
  /** Pose numbers while he flies; the wingbeat itself is laid on by the motion. */
  flying: { fly: 1, feet: 0, wing: 40, lid: 0.08, brow: 0.3, tail: 0, tailFan: 1, crest: -0.4, lean: -6, lift: 0, squash: 0 },
  draw: (p, uid) => wren.draw(p, uid),
};

/** The whole SVG for one pose, for server rendering and the icons. */
export function svgFor(poseName = 'idle', uid = 'm', extra = {}) {
  const { defs, body } = rig.draw({ ...poses[poseName], ...extra }, uid);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${rig.viewBox}" overflow="visible">${defs}${body}</svg>`;
}
