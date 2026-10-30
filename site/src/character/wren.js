// Milo the wren, drawn the way the app draws him: a port of app/Sources/MiloKit/Views/Wren/WrenRig.swift
// to SVG. Same figure space (200 x 200, y down, feet on y = 182), same parts in the same order, same
// numbers, so a pose looks the same here as on a Mac. Young and round, with a fluffy three-feather
// tuft, soft lavender brows, big low eyes with two catchlights and a sparkle, pink cheeks and a slim
// marigold scarf with a short loose end.
import { Defs, extras, rotPt, pose as mergePose } from './lib.js';

export const name = 'Wren';

export const C = {
  bodyHi: '#CBC2F4', bodyMid: '#9D90DD', bodyLo: '#6A5BB4', lidLine: '#3F3373',
  bellyHi: '#FEF5EA', bellyLo: '#F1D6BC',
  brow: '#6F5FBE', crestHi: '#B4A8EC', crestLo: '#7E6ECB', fluff: '#F4F0FF',
  wingHi: '#8A7CCB', wingLo: '#54468F', wingBar: '#B9AEEA',
  tail: '#6C5DB2', tailLo: '#4C3F8A', tailBar: '#43377D',
  eye: '#1E1730', eyeHi: '#4F4276', sheen: '#8C7CC8',
  beakHi: '#E6B274', beakLo: '#B27744', mouth: '#6E2F3C', tongue: '#C25466',
  scarfHi: '#F4C262', scarfLo: '#D69A3C', scarfRib: '#FBDB98', scarfEdge: '#FFE6B0',
  feet: '#B17C50', blush: '#EE9AA6',
  shade: '#2E2463', ground: '#2A2050', rim: '#F1ECFF', ink: '#1B1430',
  mark: '#7C6CD0',
};

export const GROUND = 182;
/** The top of his head, figure y. A little wider than tall, like a sparrow fluffed up in the cold. */
export const BODY_TOP = 68;
const SCARF_Y = 131;
const EYE_ANGLE = 30, EYE_Y = 111;
const R = 52;

/**
 * The rest pose. `lid`, `lower`, `eye`, `brow`, `browTilt`, `wing` and `open` set both sides at once;
 * `lidL`, `lidR`... override one side. At rest his head tilts 3 degrees toward you, as in the app.
 */
export const defaults = {
  turn: -0.2, lean: 0, squash: 0, lift: 0, headTilt: -3, headX: 0, headY: 0,
  gazeX: 0, gazeY: 0,
  lid: 0.2, lidL: null, lidR: null, lower: 0.14, lowerL: null, lowerR: null,
  eye: 1, eyeL: null, eyeR: null,
  brow: 0, browL: null, browR: null, browTilt: 0, browTiltL: null, browTiltR: null,
  beak: 0, blush: 0.3,
  wing: 0, wingL: null, wingR: null, open: 0, openL: null, openR: null, fly: 0,
  tail: 0, tailFan: 0,
  scarf: 0, scarfToss: 0, scarfUp: 0,
  feet: 1, crest: 0, crestSway: 0, breath: 0,
  small: false, extras: [],
};

/** The numbers the rig draws from, each on its own spring: [response in seconds, damping]. */
export const springs = {
  turn: [0.45, 0.85], lean: [0.42, 0.6], squash: [0.2, 0.42], lift: [0.26, 0.6],
  headTilt: [0.5, 0.48], headX: [0.32, 0.55], headY: [0.32, 0.55],
  gazeX: [0.09, 0.92], gazeY: [0.09, 0.92],
  lidL: [0.12, 0.9], lidR: [0.12, 0.9], lowerL: [0.12, 0.9], lowerR: [0.12, 0.9],
  eyeL: [0.18, 0.7], eyeR: [0.18, 0.7],
  browL: [0.2, 0.62], browR: [0.2, 0.62], browTiltL: [0.2, 0.62], browTiltR: [0.2, 0.62],
  beak: [0.1, 0.7], blush: [0.6, 1],
  wingL: [0.26, 0.5], wingR: [0.26, 0.5], openL: [0.24, 0.8], openR: [0.24, 0.8], fly: [0.32, 0.85],
  tail: [0.38, 0.32], tailFan: [0.3, 0.6],
  scarf: [0.75, 0.22], scarfToss: [0.36, 0.55], scarfUp: [0.6, 0.9],
  feet: [0.2, 1], crest: [0.26, 0.5], crestSway: [0.4, 0.28],
};

/** Closer than this to its target, at rest, a number counts as settled. */
export const epsilon = (k) =>
  ['lean', 'headTilt', 'wingL', 'wingR', 'tail', 'scarf', 'crestSway'].includes(k) ? 0.05
    : ['lift', 'headX', 'headY'].includes(k) ? 0.02 : 0.002;

export const smooth = (a, b, x) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
const rad = (d) => (d * Math.PI) / 180;
/** Positions to a tenth of a unit, scales and opacities to a thousandth. */
const f = (n) => Math.round(n * 10) / 10;
const g = (n) => Math.round(n * 1000) / 1000;
const pt = (x, y) => `${f(x)} ${f(y)}`;
const tf = (...parts) => parts.join(' ');
const T = (x, y) => `translate(${f(x)} ${f(y)})`;
const Rot = (d) => `rotate(${g(d)})`;
const S = (x, y = x) => `scale(${g(x)} ${g(y)})`;
const op = (a) => (a < 0.999 ? ` opacity="${g(a)}"` : '');
const strokeAttrs = (color, width, alpha = 1, cap = 'round') =>
  `fill="none" stroke="${color}" stroke-width="${width}" stroke-linecap="${cap}" stroke-linejoin="round"${op(alpha)}`;

export function bodyPath(t, scarfUp) {
  const top = BODY_TOP + scarfUp * 2;
  const xr = 160 + Math.max(t, 0) * 5, xl = 40 + Math.min(t, 0) * 5;
  return `M${pt(100 + t * 9, top)} C${pt(137 + t * 6, top)} ${pt(xr, top + 30)} ${pt(xr, 130)} C${pt(xr, 162)} 136 180 100 180 C64 180 ${pt(xl, 162)} ${pt(xl, 130)} C${pt(xl, top + 30)} ${pt(63 + t * 8, top)} ${pt(100 + t * 9, top)}Z`;
}

/** The tuft: three soft feathers fanning up from one root at (0, 0). `perk` 0...1 spreads and lifts them. */
export function crestPath(perk) {
  let d = '';
  for (const [angle, length, w] of [[-32, 25, 10], [-6, 33, 12], [22, 22, 9.5]]) {
    const L = length * (1 + perk * 0.2);
    const a = angle * (1 + perk * 0.3);
    const p = (x, y) => { const [rx, ry] = rotPt([x, y], a, [0, 0]); return pt(rx, ry); };
    d += `M0 0 C${p(w * 0.75, -L * 0.3)} ${p(w * 0.7, -L * 0.85)} ${p(w * 0.2, -L)} C${p(-w * 0.45, -L * 0.8)} ${p(-w * 0.6, -L * 0.3)} 0 0Z`;
  }
  return d;
}

export function draw(input, uid) {
  const p = mergePose(defaults, input);
  const small = !!p.small;
  const d = new Defs(uid);
  const t = p.turn, th = t * 50;
  const fx = (a) => 100 + R * Math.sin(rad(a));
  const flight = smooth(0.3, 0.7, p.fly);

  // --- paint helpers
  const linear = (key, c0, c1, top, bottom) => {
    d.raw(`<linearGradient id="${d.id(key)}" gradientUnits="userSpaceOnUse" x1="0" y1="${f(top)}" x2="0" y2="${f(bottom)}"><stop offset="0" stop-color="${c0}"/><stop offset="1" stop-color="${c1}"/></linearGradient>`);
    return d.url(key);
  };
  const softs = new Map();
  /** An ellipse that fades to nothing at its edge: shadows, occlusion, light. */
  const soft = (cx, cy, rx, ry, color, alpha, rotation = 0) => {
    const key = `soft${color.slice(1)}${Math.round(alpha * 100)}`;
    if (!softs.has(key)) {
      d.raw(`<radialGradient id="${d.id(key)}"><stop offset="0" stop-color="${color}" stop-opacity="${alpha}"/><stop offset="0.45" stop-color="${color}" stop-opacity="${g(alpha * 0.55)}"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>`);
      softs.set(key, d.url(key));
    }
    const turn = rotation ? ` transform="${T(cx, cy)} ${Rot(rotation)}"` : '';
    const [x, y] = rotation ? [0, 0] : [cx, cy];
    return `<ellipse cx="${f(x)}" cy="${f(y)}" rx="${f(rx)}" ry="${f(ry)}" fill="${softs.get(key)}"${turn}/>`;
  };
  /** The body's gradient, in figure space, so lids and cheek tufts paint with it and vanish into him. */
  const bodyGrad = (key, cx, cy, transform = '') => {
    d.raw(`<radialGradient id="${d.id(key)}" gradientUnits="userSpaceOnUse" cx="${f(cx)}" cy="${f(cy)}" r="108"${transform ? ` gradientTransform="${transform}"` : ''}><stop offset="0" stop-color="${C.bodyHi}"/><stop offset="0.5" stop-color="${C.bodyMid}"/><stop offset="1" stop-color="${C.bodyLo}"/></radialGradient>`);
    return d.url(key);
  };
  const bcx = 84 + t * 12, bcy = 98;

  const out = [];

  // --- ground shadow: shrinks and fades as he rises; gone while he flies
  const lift = p.lift + p.fly * 16;
  const ss = Math.max(0.35, 1 - lift / 70);
  const shadowOp = (1 - flight) * (0.4 + 0.6 * ss);
  if (shadowOp > 0.001) out.push(`<g transform="${T(100, GROUND + 1)} ${S(ss)}"${op(shadowOp)}>${soft(0, 0, 46, 7.5, C.ground, 0.24)}</g>`);

  const parts = []; // [z, svg], back to front
  const add = (z, svg) => parts.push([z, svg]);

  // --- feet
  const feetOp = p.feet * (1 - flight);
  if (feetOp > 0.001) {
    let fd = '';
    for (const x of [87 + t * 8, 113 + t * 8]) {
      fd += `M${f(x)} 174L${f(x)} 181M${f(x - 5)} 182L${f(x)} 180.5L${f(x + 5.5)} 182M${f(x)} 180.5L${f(x + 1.4)} 182.6`;
    }
    add(0, `<path d="${fd}" ${strokeAttrs(C.feet, small ? 3.2 : 2.4, feetOp)}/>`);
  }

  // --- tail: one barred feather fan cocked up behind his back, on the side he faces away from
  const back = t > 0.02 ? -1 : 1;
  {
    const L = 64 * (1 - p.fly * 0.3);
    const w = Math.round((7.5 + Math.max(p.tailFan, p.fly) * 3.5) * 4) / 4;
    const angle = back * (27 + p.tail * 0.8 + Math.abs(t) * 10 + p.fly * 42);
    let path = `M${pt(-w * 0.5, 0)} C${pt(-w * 0.75, -L * 0.45)} ${pt(-w - 1.2, -L * 0.78)} ${pt(-w, -L + 2)}`;
    for (const cx of [-w * 0.33, w * 0.33, w]) path += ` Q${pt(cx - w * 0.36, -L - 3.2)} ${pt(cx, -L - 0.6)}`;
    path += ` C${pt(w + 1.2, -L * 0.78)} ${pt(w * 0.75, -L * 0.45)} ${pt(w * 0.5, 0)}Z`;
    let svg = `<path d="${path}" fill="${linear('tail', C.tail, C.tailLo, -L - 3, 0)}"/>`;
    if (!small) {
      const bars = [0.56, 0.7, 0.84].map((y) => `M${pt(-w * 0.85, -L * y + 1.8)} Q${pt(0, -L * y - 1.6)} ${pt(w * 0.85, -L * y + 1.8)}`).join('');
      svg += `<path d="${bars}" ${strokeAttrs(C.tailBar, 1.7, 0.5)} clip-path="${d.clip('tailclip', `<path d="${path}"/>`)}"/>`;
      svg += `<path d="M${pt(-w + 2, -L + 6)} Q${pt(0, -L - 1)} ${pt(w - 3, -L + 5)}" ${strokeAttrs('#fff', 1, 0.25)}/>`;
    }
    add(1, `<g transform="${T(100 + back * (30 + Math.abs(t) * 34), 152)} ${Rot(angle)}">${svg}</g>`);
  }

  // --- wings: each a folded wing and an open one, cross-faded as it opens so the shape never swaps.
  // Turned far enough, the far wing slips behind him; open, it shows behind the body instead.
  const far = t > 0.05 ? 'R' : t < -0.05 ? 'L' : null;
  const farHidden = smooth(0.2, 0.3, Math.abs(t));
  for (const side of ['L', 'R']) {
    const s = side === 'L' ? -1 : 1;
    const angle = p[`wing${side}`];
    const open = Math.max(p.fly, p[`open${side}`]);
    const shown = smooth(0.2, 0.5, open);
    const folded = 1 - smooth(0.45, 0.75, open);
    const x = (side === 'L' ? 48 : 152) + t * 20;
    const isFar = far === side;
    const foldOp = folded * (isFar ? 1 - farHidden : 1);
    if (foldOp > 0.001) {
      add(4, `<g transform="${T(x, 127)} ${Rot(-s * (angle + open * 80))} ${S(0.82, 0.8)}"${op(foldOp)}>${foldedWing(s, 42, small, linear(`wingF${side}`, C.wingHi, C.wingLo, -5, 42))}</g>`);
    }
    if (shown > 0.001) {
      add(isFar ? 2 : 4, `<g transform="${T(x, 123)} ${Rot(-s * (angle - (1 - open) * 80))}"${op(shown)}>${openWing(s, 0.72, small, linear(`wingO${side}`, C.wingHi, C.wingLo, -24 * 0.72, 11 * 0.72))}</g>`);
    }
  }

  // --- body, belly, shading and the scarf band
  {
    const top = BODY_TOP + p.scarfUp * 2;
    const body = bodyPath(t, p.scarfUp);
    const clip = d.clip('bodyclip', `<path d="${body}"/>`);
    const inside = [];
    inside.push(`<path d="${body}" fill="${bodyGrad('body', bcx, bcy)}"/>`);
    const bellyX = 100 + R * Math.sin(rad(th * 0.75));
    inside.push(`<ellipse cx="${f(bellyX)}" cy="155" rx="${f(37 - Math.abs(t) * 4)}" ry="31" fill="${linear('belly', C.bellyHi, C.bellyLo, 124, 186)}"/>`);
    // ambient occlusion where he meets the ground, and the key light on his crown
    inside.push(soft(100, 190, 78, 30, C.shade, 0.26));
    inside.push(soft(76 + t * 8, top + 16, 24, 12, '#ffffff', 0.36, -24));
    if (!small) {
      // soft feather ticks around his crown, so his head isn't a bare ball
      const ticks = [[86, 81, 5], [114, 81, 5], [92, 87, 4.4], [108, 87, 4.4], [100, 84, 4]]
        .map(([x, y, w]) => { const cx = x + t * 12; return `M${pt(cx - w / 2, y)} Q${pt(cx, y + 2.6)} ${pt(cx + w / 2, y)}`; }).join('');
      inside.push(`<path d="${ticks}" ${strokeAttrs(C.fluff, 1.1, 0.32)}/>`);
    }
    // scarf band, with the soft shadow it casts on him
    const sy = SCARF_Y - p.scarfUp * 4;
    const band = `M34 ${f(sy - 6)} Q100 ${f(sy + 8)} 166 ${f(sy - 6)} L166 ${f(sy + 3)} Q100 ${f(sy + 18)} 34 ${f(sy + 3)}Z`;
    inside.push(`<path d="${band}" fill="${C.shade}" opacity="0.3" transform="translate(0 2.5)" filter="${d.blur('bandshadow', 2)}"/>`);
    inside.push(`<path d="${band}" fill="${linear('band', C.scarfHi, C.scarfLo, sy - 4, sy + 12)}"/>`);
    if (!small) {
      let ribs = '';
      for (let i = 0; i <= 16; i++) {
        const x = 44 + i * 7;
        const y = sy - 6 + (1 - ((x - 100) / 66) ** 2) * 7;
        ribs += `M${pt(x, y + 2)}L${pt(x + 0.5, y + 8.5)}`;
      }
      inside.push(`<path d="${ribs}" ${strokeAttrs(C.scarfRib, 1, 0.4)}/>`);
    }
    inside.push(`<path d="M34 ${f(sy - 6)} Q100 ${f(sy + 8)} 166 ${f(sy - 6)}" ${strokeAttrs(C.scarfEdge, 1.4, 0.7)}/>`);
    // rim light: a soft crescent on the side away from the key light
    d.raw(`<mask id="${d.id('rim')}" maskUnits="userSpaceOnUse" x="0" y="0" width="200" height="200"><path d="${body}" fill="#fff"/><path d="${body}" fill="#000" transform="translate(-5 3.5)" filter="${d.blur('rimblur', 1.5)}"/></mask>`);
    inside.push(`<path d="${body}" fill="${C.rim}" opacity="0.55" mask="${d.url('rim')}"/>`);
    let svg = `<g clip-path="${clip}">${inside.join('')}</g>`;
    // fluffy cheeks: two little feather points poking out at each side of his face, in his own colours
    let tufts = '';
    for (const side of [-1, 1]) {
      const edge = side < 0 ? 40.6 + Math.min(t, 0) * 5 : 159.4 + Math.max(t, 0) * 5;
      for (const [y, len] of [[109, 4.2], [117, 3.6]]) {
        tufts += `M${pt(edge - side * 2, y - 4)} Q${pt(edge + side * len * 0.7, y - 2.5)} ${pt(edge + side * len, y + 1.5)} Q${pt(edge + side * 0.6, y + 2.6)} ${pt(edge - side * 2, y + 4)}Z`;
      }
    }
    svg += `<path d="${tufts}" fill="${d.url('body')}"/>`;
    add(3, svg);
  }

  // --- the scarf's loose end, swinging from the knot, and the knot over it
  {
    const sy = SCARF_Y - p.scarfUp * 4;
    const knotX = fx(th + 32);
    const knotY = sy + 6 + (1 - ((knotX - 100) / 60) ** 2) * 2;
    const E = 25 * (1 + p.scarfToss * 0.25);
    const endAngle = -12 + p.scarf + p.scarfToss * -118 + p.fly * -70;
    const fill = linear('scarfend', C.scarfHi, C.scarfLo, 0, E + 2);
    let svg = `<path d="M-5 0 C${pt(-5.8, E * 0.4)} ${pt(-6.8, E * 0.8)} ${pt(-7, E)} Q${pt(0, E + 3)} ${pt(7, E + 1.5)} C${pt(6, E * 0.7)} ${pt(5.4, E * 0.35)} 5 0Z" fill="${fill}"/>`;
    svg += `<path d="M-6 0L6 0" ${strokeAttrs(C.shade, 2, 0.18, 'butt')}/>`;
    if (!small) {
      svg += `<path d="M-1.8 4L${pt(-2.4, E - 1)}M2 4L${pt(2.4, E)}" ${strokeAttrs(C.scarfRib, 1, 0.5)}/>`;
      const fringe = [-5, -1.7, 1.7, 5].map((x) => `M${pt(x, E + 1.5)}L${pt(x * 1.08, E + 5)}`).join('');
      svg += `<path d="${fringe}" ${strokeAttrs(C.scarfLo, 1.5)}/>`;
    }
    add(5, `<g transform="${T(knotX, knotY)} ${Rot(endAngle)}">${svg}</g>`);
    add(6, `<g transform="${T(knotX, knotY)}"><ellipse rx="6.5" ry="5.5" fill="${linear('knot', C.scarfHi, C.scarfLo, -5.5, 5.5)}"/><path d="M-4 -0.8 Q0 1.6 4 -0.8" ${strokeAttrs(C.scarfLo, 1.2, 0.7)}/></g>`);
  }

  // --- the face group's transform: it tilts and shifts with his head
  const fpx = fx(th), fpy = EYE_Y + 4;
  const faceT = tf(T(fpx + p.headX, fpy + p.headY), Rot(p.headTilt), T(-fpx, -fpy));

  // --- crest: a fluffy tuft rooted in his crown, behind his head. It turns with his head, perks up and
  // lies back with his mood, and sways behind every move.
  {
    const perk = Math.round(Math.min(1, Math.max(-1, p.crest)) * 100) / 100;
    const laid = Math.max(0, -perk), up = Math.max(0, perk);
    const crestAngle = p.crestSway + back * laid * 40 + t * 12;
    let svg = `<path d="${crestPath(up)}" fill="${linear('crest', C.crestLo, C.crestHi, -40, -4)}"/>`;
    if (!small) svg += `<path d="M-1.5 -10 Q-3.4 -19 ${pt(0.5, -27 - up * 6)}" ${strokeAttrs('#fff', 1, 0.35)}/>`;
    add(2, `<g transform="${faceT} ${T(100 + t * 14, BODY_TOP + 11)} ${Rot(crestAngle)} ${S(1, 1 - laid * 0.3)}">${svg}</g>`);
  }

  // --- face
  const face = [];
  const gx = p.gazeX * 4.5, gy = p.gazeY * 3.5;
  const eyeY = EYE_Y + gy - p.scarfUp * 3;
  const eyes = [['L', th - EYE_ANGLE], ['R', th + EYE_ANGLE]];
  if (p.blush > 0.01) {
    const spots = eyes.map(([side, a]) => soft(fx(a + (side === 'L' ? -10 : 10)) + gx, eyeY + 12, 6 * Math.cos(rad(a)) + 3, 5, C.blush, 0.7)).join('');
    face.push(`<g${op(Math.min(1, p.blush))}>${spots}</g>`);
  }
  const look = [Math.round(p.gazeX * 10) / 10, Math.round(p.gazeY * 10) / 10];
  const brows = [];
  for (const [side, a] of eyes) {
    const s = side === 'L' ? -1 : 1;
    const x = fx(a) + gx;
    const fore = Math.max(0.35, Math.cos(rad(a)));
    // the lid only starts covering the eye past its rest value (0.2), so at rest his eyes are wide open
    const lid = Math.max(0, (p[`lid${side}`] - 0.2) / 0.8);
    const lower = p[`lower${side}`];
    const es = p[`eye${side}`] * (small ? 1.3 : 1);
    face.push(`<g transform="${T(x, eyeY)}">${eye(d, side, lid, lower, fore * es, es, look, [bcx - x, bcy - eyeY], bodyGrad)}</g>`);
    // brow: a short soft mark in a deeper lavender, high over the eye
    const raise = p[`brow${side}`] * 4.5;
    const tilt = p[`browTilt${side}`] * 16 * s;
    brows.push(`<path d="M${pt(-4.2 * fore, 1)} Q0 -2.4 ${pt(4.2 * fore, 1)}" ${strokeAttrs(C.brow, small ? 4 : 3, small ? 0.8 : 0.7)} transform="${T(x + s * 1.5, eyeY - 20 - raise)} ${Rot(tilt)}"/>`);
  }
  face.push(...brows);
  // beak: small, low between the eyes; the tip swings toward the turn
  {
    const bx = fx(th) + gx * 1.1, by = EYE_Y + 7 + gy - p.scarfUp * 3;
    const tip = t * 9 + p.gazeX * 2;
    const open = Math.round(Math.min(1, Math.max(0, p.beak)) * 20) / 20;
    face.push(`<g transform="${T(bx, by)} ${S(0.9, 0.7)}">${beak(d, open, tip, t, linear)}</g>`);
  }

  // --- put him together: everything leans, lifts and squashes about his feet; the face tilts on top
  const breathe = p.breath * 0.012;
  const bodyT = tf(
    T(0, -lift),
    `rotate(${g(p.lean)} 100 ${GROUND})`,
    `translate(100 ${GROUND})`, S(1 - p.squash * 0.6 - breathe * 0.3, 1 + p.squash + breathe), `translate(-100 -${GROUND})`,
  );
  parts.sort((a, b) => a[0] - b[0]);
  out.push(`<g transform="${bodyT}">${parts.map((x) => x[1]).join('')}<g transform="${faceT}">${face.join('')}</g></g>`);
  if (p.extras?.length) out.push(extras(p.extras, C.mark, { x: 100, y: 56 - lift, warm: C.scarfLo }));
  return { defs: d.toString(), body: out.join('') };
}

function foldedWing(s, L, small, fill) {
  const path = `M${pt(2 * s, -5)} C${pt(-9 * s, -5)} ${pt(-15 * s, 8)} ${pt(-15 * s, L * 0.42)} C${pt(-15 * s, L * 0.72)} ${pt(-9 * s, L * 0.9)} ${pt(-4 * s, L)} C${pt(4 * s, L * 0.82)} ${pt(11 * s, L * 0.6)} ${pt(11 * s, L * 0.36)} C${pt(11 * s, 8)} ${pt(10 * s, -5)} ${pt(2 * s, -5)}Z`;
  let svg = `<path d="${path}" fill="${fill}"/>`;
  if (!small) {
    const bars = [0.56, 0.7, 0.84].map((k, i) => `M${pt(-12 * s + i * 2.5 * s, L * k)} Q${pt(-4 * s, L * k + 2.6)} ${pt(5 * s - i * 2.5 * s, L * k - 1.5)}`).join('');
    svg += `<path d="${bars}" ${strokeAttrs(C.wingBar, 1.3, 0.4)}/>`;
  }
  return svg;
}

function openWing(s, k, small, fill) {
  const q = (x, y) => pt(s * x * k, y * k);
  const path = `M${q(0, -6)} C${q(16, -16)} ${q(40, -24)} ${q(62, -20)} Q${q(68, -17)} ${q(62, -12)} Q${q(66, -8)} ${q(58, -5)} Q${q(61, 0)} ${q(52, 1)} Q${q(54, 6)} ${q(44, 6)} Q${q(44, 11)} ${q(34, 10)} C${q(22, 10)} ${q(8, 9)} ${q(0, 6)}Z`;
  let svg = `<path d="${path}" fill="${fill}"/>`;
  if (!small) {
    const bars = [[30, -14, 32, 7], [42, -17, 44, 3], [52, -18, 53, 0]].map(([a, b, c, e]) => `M${q(a, b)}L${q(c, e)}`).join('');
    svg += `<path d="${bars}" ${strokeAttrs(C.wingBar, 1.2, 0.45)}/>`;
    svg += `<path d="M${q(4, -6)} C${q(18, -14)} ${q(40, -21)} ${q(60, -19)}" ${strokeAttrs('#fff', 1.2, 0.3)}/>`;
  }
  return svg;
}

const lidPath = (yl, sag) => `M-12 -13L12 -13L12 ${f(yl)} Q0 ${f(yl + sag)} -12 ${f(yl)}Z`;

/** One eye at the origin: big and dark, two catchlights and a sparkle, lids in his own colours. */
function eye(d, side, lid, lower, sx, sy, look, center, bodyGrad) {
  const rx = 9.2, ry = 10.4;
  const yl = -ry + lid * ry * 2.1;
  const sag = -1.6 + 5 * lid * lid;
  const yb = ry - lower * ry * 1.25;
  const smile = smooth(0.7, 0.9, lower);
  const o = [];
  if (smile < 1) {
    const inner = [];
    if (lid < 0.97) {
      const clip = d.clip(`eye${side}`, `<ellipse rx="${rx}" ry="${ry}"/>`);
      d.raw(`<radialGradient id="${d.id(`iris${side}`)}" gradientUnits="userSpaceOnUse" cx="0" cy="${f(ry * 0.7)}" r="${f(ry * 1.5)}"><stop offset="0" stop-color="${C.eyeHi}"/><stop offset="1" stop-color="${C.eye}"/></radialGradient>`);
      if (!d.items.some((s) => s.includes(`id="${d.id('sheen')}"`))) {
        d.raw(`<radialGradient id="${d.id('sheen')}"><stop offset="0" stop-color="${C.sheen}" stop-opacity="0.35"/><stop offset="0.45" stop-color="${C.sheen}" stop-opacity="0.19"/><stop offset="1" stop-color="${C.sheen}" stop-opacity="0"/></radialGradient>`);
      }
      inner.push(`<g clip-path="${clip}"><ellipse rx="${rx}" ry="${ry}" fill="${d.url(`iris${side}`)}"/>`
        // a soft sheen across the lower half, then the key catchlight, a small second one and a sparkle
        + `<ellipse cx="-1" cy="5" rx="6.5" ry="3.6" fill="${d.url('sheen')}"/>`
        + `<circle cx="${f(2.6 + look[0] * 0.7)}" cy="${f(-3.4 + look[1] * 0.6)}" r="3.8" fill="#fff"/>`
        + `<circle cx="-3.3" cy="3.9" r="1.7" fill="#fff" opacity="0.85"/>`
        + `<circle cx="${f(-2.85 + look[0] * 0.5)}" cy="${f(-4.85 + look[1] * 0.4)}" r="0.75" fill="#fff" opacity="0.7"/>`
        // the shadow the upper lid casts on the eye
        + `<path d="${lidPath(yl + 1.6, sag)}" fill="${C.ink}" opacity="0.3"/></g>`);
    }
    // lids paint with the body's own gradient, so at rest they disappear into him
    let lids = lidPath(yl, sag);
    if (lower > 0.001) lids += `M-12 13L-12 ${f(yb + 3)} Q0 ${f(yb - 6)} 12 ${f(yb + 3)}L12 13Z`;
    const big = d.clip(`eyebig${side}`, `<ellipse rx="${rx + 1.2}" ry="${ry + 1.2}"/>`);
    const fill = bodyGrad(`lid${side}`, center[0], center[1], `scale(${g(1 / sx)} ${g(1 / sy)})`);
    inner.push(`<path d="${lids}" fill="${fill}" clip-path="${big}"/>`);
    if (lid > 0.04) {
      const closed = Math.min(yl, ry - 0.5);
      inner.push(`<path d="M${f(-rx - 0.4)} ${f(closed)} Q0 ${f(closed + sag)} ${f(rx + 0.4)} ${f(closed)}" ${strokeAttrs(C.lidLine, lid > 0.95 ? 2.1 : 1.1, lid > 0.95 ? 1 : 0.6 + 0.4 * smooth(0.5, 0.95, lid))}/>`);
    }
    if (lower > 0.3) {
      const k = smooth(0.4, 0.8, lower);
      inner.push(`<path d="M${f(-rx + 0.5)} ${f(yb + 2.6)} Q0 ${f(yb - 5.6)} ${f(rx - 0.5)} ${f(yb + 2.6)}" ${strokeAttrs(C.lidLine, g(1 + 0.8 * k), 0.5 + 0.4 * k)}/>`);
    }
    o.push(`<g${op(1 - smile)}>${inner.join('')}</g>`);
  }
  // smiling: a clean arch
  if (smile > 0) o.push(`<path d="M-7.6 4.8 Q0 -6 7.6 4.8" ${strokeAttrs(C.eye, 3, smile)}/>`);
  return `<g transform="${S(sx, sy)}">${o.join('')}</g>`;
}

/** The beak: a short upper bill pointing down at you, the lower bill swinging down below it to open. */
function beak(d, open, tip, t, linear) {
  const dd = open * 11;
  const upperTip = 13 - open * 3;
  let svg = '';
  if (open > 0.03) {
    svg += `<path d="M-6 ${f(3 + dd * 0.4)} Q${pt(-2.8, 8.5 + dd)} ${pt(tip * 0.8 - 0.4, 10.5 + dd)} Q${pt(2.6, 8.5 + dd)} ${pt(6, 3 + dd * 0.4)}Z" fill="${linear('beaklo', C.beakHi, C.beakLo, 3, 11 + dd)}"/>`;
    // the mouth inside it, with a hint of tongue once it is properly open
    const mouth = `M-5 2.5 Q${pt(-2.6, 6 + dd * 0.8)} ${pt(tip * 0.8 - 0.3, 8.2 + dd * 0.86)} Q${pt(2.4, 6 + dd * 0.8)} 5 2.5Z`;
    svg += `<path d="${mouth}" fill="${C.mouth}"/>`;
    if (open > 0.3) {
      const k = smooth(0.3, 0.8, open);
      const h = 5 * k + 1;
      svg += `<ellipse cx="${f(tip * 0.6)}" cy="${f(5 + dd * 0.62 + h / 2)}" rx="3.4" ry="${f(h / 2)}" fill="${C.tongue}" clip-path="${d.clip('mouth', `<path d="${mouth}"/>`)}"/>`;
    }
  }
  svg += `<path d="M-6.5 0 Q0 -4.5 6.5 0 Q${pt(3 + t * 3, 6)} ${pt(tip, upperTip)} Q${pt(-3 + t * 3, 6)} -6.5 0Z" fill="${linear('beakup', C.beakHi, C.beakLo, -4, 13)}"/>`;
  svg += `<path d="M-3 -1.2 Q0 -2.6 2.5 -1.4" ${strokeAttrs('#fff', 1, 0.5)}/>`;
  return svg;
}
