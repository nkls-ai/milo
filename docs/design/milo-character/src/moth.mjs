// Concept B: Milo the lamp moth. A fluffy lavender moth who lives by the light of your screen: feathery
// antennae that work as eyebrows, a cream ruff, and folded wings like a cardigan with two marigold "lamp"
// spots.
import { Defs, GROUND, extras, f, pose as mergePose, rad, rot, scaleAt, cursor } from './lib.mjs';

export const name = 'Moth';

export const C = {
  furHi: '#CFC4F4', furMid: '#A496E0', furLo: '#6C5DB4', lidLine: '#3F3373',
  ruffHi: '#FCF6EC', ruffLo: '#E6D3BB',
  wingHi: '#C3B2EC', wingMid: '#9A86D2', wingLo: '#6E5BAE', fringe: '#F4ECDF',
  spot: '#F0B649', spotRing: '#8C5A2B', hind: '#E9A9B8',
  antenna: '#E8CF9E', antennaLo: '#B48A55',
  eye: '#1E1730', eyeHi: '#54477C', mouth: '#6E2F3C', blush: '#EE9AA6',
  limb: '#5B4B9C', mark: '#7C6CD0',
};

export const defaults = {
  turn: -0.15, lean: 0, squash: 0, lift: 0, headTilt: 0,
  gx: 0, gy: 0,
  lid: 0.14, lidL: null, lidR: null, lower: 0, lowerL: null, lowerR: null,
  eyeScale: 1, eyeScaleL: null, eyeScaleR: null,
  brow: 0, browL: null, browR: null, browTilt: 0, browTiltL: null, browTiltR: null,
  mouth: 0, smile: 0.08, blush: 0,
  armL: 0, armR: 0, fly: 0, wrap: 0, flutter: 0,
  feet: 1, extras: [], cursorAt: null, small: false,
};

/// A fur outline: an ellipse whose edge is made of soft bumps.
function fuzz(cx, cy, rx, ry, n, bump, phase = 0) {
  let d = '';
  for (let i = 0; i <= n; i++) {
    const a = ((i + phase) / n) * Math.PI * 2;
    const x = cx + rx * Math.cos(a), y = cy + ry * Math.sin(a);
    if (i === 0) { d += `M${f(x)} ${f(y)}`; continue; }
    const m = ((i - 0.5 + phase) / n) * Math.PI * 2;
    const k = 1 + bump * (0.85 + 0.3 * Math.sin(i * 2.7));
    d += ` Q${f(cx + rx * k * Math.cos(m))} ${f(cy + ry * k * Math.sin(m))} ${f(x)} ${f(y)}`;
  }
  return d + 'Z';
}

export function draw(input, uid) {
  const p = mergePose(defaults, input);
  const d = new Defs(uid);
  const t = p.turn, th = t * 50;
  const sinA = (a) => Math.sin(rad(a)), cosA = (a) => Math.cos(rad(a));
  const soft = d.blur('soft', 2), softer = d.blur('softer', 5), ground = d.blur('ground', 2.6);
  const out = [], fig = [];
  const lift = p.lift + p.fly * 18;

  const ss = Math.max(0.35, 1 - lift / 70);
  out.push(`<ellipse cx="100" cy="${GROUND + 1}" rx="${f(40 * ss)}" ry="${f(5.5 * ss)}" fill="#2A2050" opacity="${f(0.22 * ss)}" filter="${ground}"/>`);

  const furStops = `<stop offset="0" stop-color="${C.furHi}"/><stop offset="0.55" stop-color="${C.furMid}"/><stop offset="1" stop-color="${C.furLo}"/>`;
  const furGrad = (name, transform = '') => {
    d.raw(`<radialGradient id="${d.id(name)}" gradientUnits="userSpaceOnUse" cx="${f(84 + t * 12)}" cy="78" r="110"${transform ? ` gradientTransform="${transform}"` : ''}>${furStops}</radialGradient>`);
    return d.url(name);
  };
  const fur = furGrad('fur');

  // ---- wings: folded down his back like a cardigan; open wide to fly
  const wingFill = d.linear('wing', [[0, C.wingHi], [0.6, C.wingMid], [1, C.wingLo]]);
  const hindFill = d.linear('hind', [[0, '#F3C6CF'], [1, C.hind]]);
  const wing = (side) => {
    const s = side === 'L' ? -1 : 1;
    const ax = 100 + s * 20 + t * 6, ay = 108;
    const fold = -s * 10 + p.fly * -s * 100 + p.flutter * -s * 8 + p.wrap * s * 40;
    const hindFold = -s * 6 + p.fly * -s * 52 + p.wrap * s * 30;
    const fore = `M0 0 C${s * 10} -4 ${s * 36} 2 ${s * 48} 18 C${s * 60} 34 ${s * 64} 58 ${s * 56} 70 C${s * 48} 80 ${s * 24} 76 ${s * 12} 62 C${s * 2} 48 ${s * 6} 22 0 0Z`;
    const fringe = p.small ? '' : `<path d="M${s * 56} 70 C${s * 48} 80 ${s * 24} 76 ${s * 12} 62" stroke="${C.fringe}" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-dasharray="0.1 3.4" opacity="0.9"/>`;
    const veins = p.small ? '' : `<path d="M${s * 4} 6 Q${s * 30} 22 ${s * 50} 58 M${s * 6} 14 Q${s * 22} 40 ${s * 30} 70" stroke="${C.wingHi}" stroke-width="1" fill="none" opacity="0.5"/>`;
    const spot = `<circle cx="${s * 38}" cy="48" r="8.2" fill="${C.spotRing}" opacity="0.55"/><circle cx="${s * 38}" cy="48" r="6.6" fill="${C.spot}"/><circle cx="${s * 36.4}" cy="46" r="2" fill="#FFF3D1"/>`;
    const hind = `<g transform="rotate(${f(hindFold)})"><path d="M0 6 C${s * 14} 10 ${s * 40} 40 ${s * 36} 64 C${s * 32} 80 ${s * 12} 76 ${s * 6} 56Z" fill="${hindFill}"/></g>`;
    return `<g transform="translate(${f(ax)} ${ay})">${hind}<g transform="rotate(${f(fold)})"><path d="${fore}" fill="${wingFill}"/>${veins}${spot}${fringe}</g></g>`;
  };
  fig.push(wing(t > 0 ? 'R' : 'L'), wing(t > 0 ? 'L' : 'R'));

  // ---- feet
  if (p.feet && p.fly < 0.5) {
    for (const x of [90 + t * 8, 110 + t * 8]) {
      fig.push(`<path d="M${f(x)} 170 L${f(x)} 180" stroke="${C.limb}" stroke-width="3" stroke-linecap="round"/><ellipse cx="${f(x + 1.5)}" cy="181" rx="4.6" ry="2.4" fill="${C.limb}"/>`);
    }
  }

  // ---- body: a round fluffy thorax
  const bodyD = fuzz(100 + t * 2, 142, 37, 37, 22, 0.07, 0.3);
  fig.push(`<path d="${bodyD}" fill="${fur}"/>`);
  const bodyClip = d.clip('bodyclip', `<path d="${bodyD}"/>`);
  fig.push(`<g clip-path="${bodyClip}"><ellipse cx="100" cy="186" rx="50" ry="22" fill="#2E2463" opacity="0.35" filter="${softer}"/><ellipse cx="${f(100 + t * 10)}" cy="152" rx="20" ry="22" fill="#fff" opacity="0.14" filter="${softer}"/></g>`);
  // belly fur marks
  if (!p.small) {
    for (const [x, y] of [[-9, 146], [6, 152], [-2, 162], [12, 163]]) {
      fig.push(`<path d="M${f(100 + t * 10 + x - 3)} ${y} l3 3.4 l3 -3.4" stroke="${C.furHi}" stroke-width="1.2" fill="none" stroke-linecap="round" opacity="0.6"/>`);
    }
  }

  // ---- arms: thin, with fuzzy mitts; resting on the tummy by default
  const arm = (side) => {
    const s = side === 'L' ? -1 : 1;
    const a = side === 'L' ? p.armL : p.armR;
    const ax = 100 + s * 22 + t * 8, ay = 130;
    const L = 13 + (a > 60 ? 10 : 0);
    const base = -s * 35; // rests angled in toward the tummy
    const ang = base - s * a;
    const ex = ax + L * Math.sin(rad(ang)), ey = ay + L * Math.cos(rad(ang));
    const mx = (ax + ex) / 2 + s * 4 * Math.cos(rad(ang)), my = (ay + ey) / 2;
    return `<path d="M${f(ax)} ${ay} Q${f(mx)} ${f(my)} ${f(ex)} ${f(ey)}" stroke="${C.limb}" stroke-width="3.2" fill="none" stroke-linecap="round"/><path d="${fuzz(ex, ey, 4.6, 4.4, 8, 0.14)}" fill="${C.furMid}"/>`;
  };
  fig.push(arm('L'), arm('R'));

  // ---- ruff: the cream collar between head and body
  const ruffD = fuzz(100 + t * 4, 119, 41, 15, 18, 0.2, 0.5);
  const ruffFill = d.linear('ruff', [[0, C.ruffHi], [1, C.ruffLo]]);
  fig.push(`<path d="${ruffD}" fill="${ruffFill}"/>`);
  if (!p.small) fig.push(`<path d="${fuzz(100 + t * 4, 116, 30, 8, 12, 0.25, 0.2)}" fill="#fff" opacity="0.35"/>`);

  // ---- head
  const hx = 100 + t * 6, hy = 87;
  const headD = fuzz(hx, hy, 37, 32, 26, 0.05);
  const head = [];
  // antennae, behind the head: feathery fronds that act as brows
  const antenna = (side) => {
    const s = side === 'L' ? -1 : 1;
    const bx = hx + s * 13 + t * 10, by = hy - 26;
    const raise = p[`brow${side}`], tilt = p[`browTilt${side}`];
    const ang = s * (8 + raise * -14 + tilt * 22) ;
    const pts = [[0, 0], [s * 6, -22], [s * 26, -36]];
    const N = p.small ? 0 : 16;
    const barbs = [];
    for (let i = 2; i <= N; i++) {
      const k = i / (N + 1);
      const x = (1 - k) ** 2 * pts[0][0] + 2 * (1 - k) * k * pts[1][0] + k ** 2 * pts[2][0];
      const y = (1 - k) ** 2 * pts[0][1] + 2 * (1 - k) * k * pts[1][1] + k ** 2 * pts[2][1];
      const len = 9 * Math.sin(Math.PI * Math.min(1, k * 1.1));
      barbs.push(`M${f(x)} ${f(y)} l${f(-s * len * 0.35)} ${f(-len)} M${f(x)} ${f(y)} l${f(s * len)} ${f(-len * 0.25)}`);
    }
    return `<g transform="translate(${f(bx)} ${f(by)}) rotate(${f(ang)})"><path d="${barbs.join(' ')}" stroke="${C.antenna}" stroke-width="1.3" stroke-linecap="round" fill="none"/><path d="M0 0 Q${pts[1][0]} ${pts[1][1]} ${pts[2][0]} ${pts[2][1]}" stroke="${C.antennaLo}" stroke-width="2.2" fill="none" stroke-linecap="round"/></g>`;
  };
  head.push(antenna('L'), antenna('R'));
  head.push(`<path d="${headD}" fill="${fur}"/>`);
  const headClip = d.clip('headclip', `<path d="${headD}"/>`);
  head.push(`<g clip-path="${headClip}"><ellipse cx="${f(hx - 14)}" cy="${hy - 22}" rx="17" ry="8" fill="#fff" opacity="0.3" transform="${rot(-20, hx - 14, hy - 22)}" filter="${soft}"/><ellipse cx="${hx}" cy="${hy + 36}" rx="40" ry="12" fill="#2E2463" opacity="0.3" filter="${softer}"/></g>`);
  // rim light
  d.raw(`<mask id="${d.id('rim')}" maskUnits="userSpaceOnUse" x="0" y="0" width="200" height="200"><path d="${headD}" fill="#fff"/><path d="${headD}" fill="#000" transform="translate(-4 3)" filter="${d.url('rimblur')}"/></mask>`);
  d.blur('rimblur', 1.5);
  head.push(`<path d="${headD}" fill="#F3EFFF" opacity="0.5" mask="${d.url('rim')}"/>`);

  // face
  const face = [];
  const R = 37;
  const gx = p.gx * 4, gy = p.gy * 3;
  const eyeY = hy + 2 + gy;
  if (p.blush > 0) {
    for (const s of [-1, 1]) face.push(`<ellipse cx="${f(hx + R * sinA(th + s * 40) + gx)}" cy="${f(eyeY + 14)}" rx="6" ry="3.4" fill="${C.blush}" opacity="${f(0.6 * p.blush)}" filter="${soft}"/>`);
  }
  for (const side of ['L', 'R']) {
    const s = side === 'L' ? -1 : 1;
    const a = th + s * 27;
    const x = hx + R * sinA(a) * 0.95 + gx;
    const fore = Math.max(0.35, cosA(a));
    const lid = p[`lid${side}`], lower = p[`lower${side}`], es = p[`eyeScale${side}`];
    const rx = 9.6, ry = 11.4;
    const yl = -ry + lid * ry * 2.1, yb = ry - lower * ry * 1.25;
    const sag = -1.8 + 6 * lid * lid;
    const eyeFill = d.radial(`eye${side}`, [[0, C.eyeHi], [1, C.eye]], { cx: 0.5, cy: 0.85, r: 0.75 });
    const clip = d.clip(`eyeclip${side}`, `<ellipse rx="${rx}" ry="${ry}"/>`);
    const big = d.clip(`eyebig${side}`, `<ellipse rx="${rx + 1.2}" ry="${ry + 1.2}"/>`);
    const lidFill = furGrad(`lid${side}`, `scale(${f(1 / (fore * es))} ${f(1 / es)}) translate(${f(-x)} ${f(-eyeY)})`);
    const ball = lid > 0.97 ? '' : `<g clip-path="${clip}"><ellipse rx="${rx}" ry="${ry}" fill="${eyeFill}"/><circle cx="${f(3 + p.gx)}" cy="${f(-3.4 + p.gy)}" r="3.1" fill="#fff"/><circle cx="-3.2" cy="4" r="1.3" fill="#fff" opacity="0.7"/></g>`;
    const lids = `<path d="M-13 -15 L13 -15 L12 ${f(yl)} Q0 ${f(yl + sag)} -12 ${f(yl)}Z" fill="#1B1430" opacity="0.3" transform="translate(0 1.6)" clip-path="${clip}"/><path d="M-13 -15 L13 -15 L12 ${f(yl)} Q0 ${f(yl + sag)} -12 ${f(yl)}Z" fill="${lidFill}"/>${lower > 0 ? `<path d="M-12 14 L-12 ${f(yb + 3)} Q0 ${f(yb - 7)} 12 ${f(yb + 3)} L12 14Z" fill="${lidFill}"/>` : ''}`;
    const closed = Math.min(yl, ry - 0.5);
    const lidLine = lid > 0.04 ? `<path d="M${-rx - 0.4} ${f(closed)} Q0 ${f(closed + sag)} ${rx + 0.4} ${f(closed)}" stroke="${C.lidLine}" stroke-width="${lid > 0.95 ? 2.2 : 1.2}" fill="none" stroke-linecap="round" opacity="${lid > 0.95 ? 1 : 0.6}"/>` : '';
    const lowerLine = lower > 0.3 ? `<path d="M${-rx + 0.5} ${f(yb + 3)} Q0 ${f(yb - 7)} ${rx - 0.5} ${f(yb + 3)}" stroke="${C.lidLine}" stroke-width="${lower > 0.7 ? 2 : 1}" fill="none" stroke-linecap="round" opacity="0.85"/>` : '';
    face.push(`<g transform="translate(${f(x)} ${f(eyeY)}) scale(${f(fore * es)} ${f(es)})">${ball}<g clip-path="${big}">${lids}</g>${lidLine}${lowerLine}</g>`);
  }
  // mouth: a small soft line, opens to a rounded shape when he talks
  const mx = hx + R * sinA(th) * 0.9 + gx * 1.1, my = hy + 17 + gy;
  if (p.mouth > 0.05) {
    face.push(`<path d="M${f(mx - 4.5)} ${f(my)} Q${f(mx)} ${f(my - 1.5)} ${f(mx + 4.5)} ${f(my)} Q${f(mx + 3.5)} ${f(my + 3 + p.mouth * 6)} ${f(mx)} ${f(my + 3.5 + p.mouth * 6)} Q${f(mx - 3.5)} ${f(my + 3 + p.mouth * 6)} ${f(mx - 4.5)} ${f(my)}Z" fill="${C.mouth}"/>`);
  } else {
    face.push(`<path d="M${f(mx - 4)} ${f(my)} Q${f(mx)} ${f(my + p.smile * 8)} ${f(mx + 4)} ${f(my)}" stroke="${C.mouth}" stroke-width="1.8" fill="none" stroke-linecap="round"/>`);
  }
  head.push(`<g>${face.join('')}</g>`);
  fig.push(`<g transform="${rot(p.headTilt, hx, hy + 20)}">${head.join('')}</g>`);

  const transform = [`translate(0 ${f(-lift)})`, rot(p.lean, 100, GROUND), scaleAt(1 - p.squash * 0.6, 1 + p.squash, 100, GROUND)].join(' ');
  out.push(`<g transform="${transform}">${fig.join('')}</g>`);
  if (p.cursorAt) out.push(cursor(p.cursorAt[0], p.cursorAt[1], 1.1, C.mark));
  out.push(extras(p.extras, C.mark, { x: 100, y: 56 - lift }));
  return { defs: d.toString(), body: out.join('') };
}

export const states = [
  ['idle', {}],
  ['listening', { lean: -4, headTilt: -6, lid: 0.06, brow: 0.9, gx: -0.3, armL: 10, armR: 10 }],
  ['thinking', { gx: -0.6, gy: -0.8, lid: 0.26, browL: 0.8, browR: -0.3, headTilt: 5, armL: 120, flutter: 1, smile: 0, extras: ['think'] }],
  ['speaking', { mouth: 0.6, lid: 0.12, brow: 0.3, armR: 30 }],
  ['working', { turn: -0.4, gx: -0.8, gy: 0.4, lid: 0.34, brow: -0.4, smile: 0, armL: 70, cursorAt: [30, 120] }],
  ['flying', { turn: -0.4, fly: 1, lean: -12, gx: -0.6, lid: 0.12, feet: 0, brow: 0.4 }],
  ['pointing', { turn: -0.35, armL: 150, gx: -0.9, gy: -0.6, lid: 0.12, brow: 0.5, lean: -4, cursorAt: [22, 58] }],
  ['happy', { lower: 0.9, lid: 0, brow: 0.8, smile: 0.6, lift: 5, squash: 0.03, blush: 0.6, flutter: 1, armL: 40, armR: 40 }],
  ['concerned', { lean: 5, browTilt: 1, brow: -0.2, lid: 0.08, eyeScale: 0.9, smile: -0.4, armL: 60, armR: 60, wrap: 0.3 }],
  ['sleepy', { lid: 1, wrap: 1, squash: -0.05, headTilt: -8, brow: -1, smile: 0.05, extras: ['zzz'] }],
  ['confused', { headTilt: 11, browR: 1, browL: -0.8, eyeScaleL: 0.8, lid: 0.12, smile: -0.2, extras: ['question'] }],
  ['quietly proud', { lid: 0.3, lower: 1, brow: 0.6, headTilt: 6, smile: 0.5, squash: 0.035, blush: 0.4, gy: -0.3, armL: 20, armR: 20, extras: ['spark'] }],
];
