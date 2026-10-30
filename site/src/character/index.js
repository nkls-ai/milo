// The one place that decides how Milo looks. Everything else on the site talks to Milo in named
// poses and gestures, and the rig turns a pose (a handful of numbers) into an SVG. To try another
// design, write a rig with the same shape as `rig` below and change the import.
//
// The wren rig is copied from docs/design/milo-character/src (track 12), unchanged apart from the
// import path.
import * as wren from './wren.js';
import { pose as mergePose } from './lib.js';

const S = Object.fromEntries(wren.states);

/** Named poses: the states from the character sheet, plus a few the site needs. */
const poses = {
  idle: {},
  listening: S.listening,
  thinking: { ...S.thinking, extras: [] },
  speaking: S.speaking,
  working: { ...S.working, cursorAt: null },
  flying: S.flying,
  pointing: { ...S.pointing, cursorAt: null },
  happy: S.happy,
  concerned: S.concerned,
  sleepy: { ...S.sleepy, extras: [] },
  confused: S.confused,
  proud: { ...S['quietly proud'], extras: [] },
  // waiting for a yes: alert, eyes on you, brows up a little
  waiting: { lid: 0.12, brow: 0.35, lean: 2, tail: 6 },
  // looking down at what he works on, the scarf already over his shoulder
  busy: { turn: -0.35, gx: -0.5, gy: 0.7, lid: 0.32, brow: -0.2, scarfToss: 1, tail: 4 },
};

/** Gestures: key poses over time, laid on top of whatever pose he is in. `ms` is how long each holds. */
const gestures = {
  // "On it": looks down, squashes, tosses the loose end of his scarf over his shoulder, settles.
  toss: [
    { ms: 180, p: { gy: 0.9, gx: 0.3, headTilt: -6, squash: -0.035, lid: 0.35 } },
    { ms: 200, p: { scarfToss: 0.5, squash: 0.04, lift: 4, wingR: 40, lid: 0.2, brow: 0.3 } },
    { ms: 320, p: { scarfToss: 1, turn: -0.35, squash: -0.02, lid: 0.3, gx: -0.6 } },
  ],
  // A small hop when he notices you.
  hop: [
    { ms: 110, p: { squash: -0.05 } },
    { ms: 170, p: { lift: 9, squash: 0.05, tail: 14, brow: 0.4 } },
    { ms: 160, p: { lift: 0, squash: -0.03 } },
  ],
  // Waves with his right wing open: up, two wags, down.
  wave: [
    { ms: 160, p: { wingOpenR: 1, wingR: 30, lid: 0.1, brow: 0.5, lower: 0.5, tail: 12, headTilt: -5 } },
    { ms: 170, p: { wingOpenR: 1, wingR: 68, lid: 0.1, brow: 0.5, lower: 0.5, tail: 16, headTilt: -5 } },
    { ms: 170, p: { wingOpenR: 1, wingR: 38, lid: 0.1, brow: 0.5, lower: 0.5, tail: 12, headTilt: 3 } },
    { ms: 170, p: { wingOpenR: 1, wingR: 68, lid: 0.1, brow: 0.5, lower: 0.5, tail: 16, headTilt: -5 } },
    { ms: 200, p: { wingOpenR: 1, wingR: 30, lid: 0.1, brow: 0.5, lower: 0.5, tail: 12 } },
  ],
  // A nod as your words arrive.
  nod: [
    { ms: 140, p: { gy: 0.7, headTilt: 3 } },
    { ms: 180, p: { gy: -0.1 } },
  ],
  // The tail tick while he waits for a yes.
  tick: [
    { ms: 120, p: { tail: 22 } },
    { ms: 160, p: { tail: 2 } },
  ],
  // The yawn before he falls asleep.
  yawn: [
    { ms: 300, p: { mouth: 0.9, lid: 0.75, brow: -0.4, squash: 0.03, headTilt: -4 } },
    { ms: 380, p: { mouth: 0.2, lid: 0.9, squash: -0.03, headTilt: -6 } },
  ],
};

/** Plain-language descriptions, for alt text. */
const describe = {
  idle: 'Milo, a small round lavender wren with pale brow stripes, a cocked tail and a marigold knitted scarf',
  listening: 'Milo leaning in to listen',
  thinking: 'Milo looking up, thinking',
  speaking: 'Milo talking',
  working: 'Milo at work, his scarf tossed over his shoulder',
  busy: 'Milo at work, his scarf tossed over his shoulder',
  flying: 'Milo flying',
  pointing: 'Milo pointing with one wing',
  happy: 'Milo smiling',
  concerned: 'Milo looking a little worried',
  sleepy: 'Milo asleep with his scarf pulled up',
  confused: 'Milo tilting his head, confused',
  proud: 'Milo looking quietly pleased',
  waiting: 'Milo waiting for an answer',
};

export const rig = {
  name: 'wren',
  viewBox: '0 0 200 200',
  defaults: wren.defaults,
  poses,
  gestures,
  describe: (name) => describe[name] ?? describe.idle,
  /** Fill per-side values (lidL, lidR...) from shared ones, so every number can be animated on its own. */
  resolve: (p) => mergePose(wren.defaults, p),
  /** Where his eyes and head go for a gaze between -1 and 1 on each axis. */
  gaze: (gx, gy) => ({ gx, gy, turn: -0.2 + gx * 0.22, headTilt: gx * 3 }),
  /** Wings while flying, at time t in seconds. */
  flap: (t) => {
    const a = 46 + Math.sin(t * 17) * 26;
    return { fly: 1, wingL: a, wingR: a, feet: 0 };
  },
  draw: (p, uid) => wren.draw(p, uid),
};

/** The whole SVG for one pose, for server rendering and the icons. */
export function svgFor(poseName = 'idle', uid = 'm', extra = {}) {
  const { defs, body } = rig.draw({ ...poses[poseName], ...extra }, uid);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${rig.viewBox}" overflow="visible">${defs}${body}</svg>`;
}
