// Concept C: Milo the house sprite. A small household helper from folklore (the kind that tidies while
// you're out), in a knitted lavender hood with a long floppy tip and a marigold tassel. The tip is his
// tell: it perks up, droops, curls into a question.
import { Defs, GROUND, curve, extras, f, pose as mergePose, rad, rot, scaleAt, taper, cursor } from './lib.mjs';

export const name = 'Sprite';

export const C = {
  hoodHi: '#C4B9F0', hoodMid: '#9A8CD8', hoodLo: '#5F50A6', rim: '#7466BE', stitch: '#D9D1FA',
  faceHi: '#F7F2FD', faceLo: '#E3D9F3', nose: '#4E3A6E', mouth: '#6E2F3C', blush: '#EE9AA6',
  eye: '#1E1730', eyeHi: '#54477C', lidLine: '#4A3D78', lid: '#EEE7F8',
  tassel: '#F0B649', tasselLo: '#C98526', boot: '#4A3C7A', bootHi: '#6C5DA8', mitt: '#F3EDFB', mittLo: '#C9B6E0',
  mark: '#7C6CD0',
};

export const defaults = {
  turn: -0.15, lean: 0, squash: 0, lift: 0, headTilt: 0,
  gx: 0, gy: 0,
  lid: 0.15, lidL: null, lidR: null, lower: 0, lowerL: null, lowerR: null,
  eyeScale: 1, eyeScaleL: null, eyeScaleR: null,
  brow: 0, browL: null, browR: null, browTilt: 0, browTiltL: null, browTiltR: null,
  mouth: 0, smile: 0.2, blush: 0.25,
  armL: 0, armR: 0, fly: 0,
  tip: 0, tipCurl: 0, tipSide: 1, brim: 0,
  feet: 1, extras: [], cursorAt: null, small: false,
};

export function draw(input, uid) {
  const p = mergePose(defaults, input);
  const d = new Defs(uid);
  const t = p.turn, th = t * 50;
  const sinA = (a) => Math.sin(rad(a)), cosA = (a) => Math.cos(rad(a));
  const soft = d.blur('soft', 2), softer = d.blur('softer', 5), ground = d.blur('ground', 2.6);
  const out = [], fig = [];
  const lift = p.lift + p.fly * 16;
  const ss = Math.max(0.35, 1 - lift / 70);
  out.push(`<ellipse cx="100" cy="${GROUND + 1}" rx="${f(40 * ss)}" ry="${f(5.5 * ss)}" fill="#2A2050" opacity="${f(0.22 * ss)}" filter="${ground}"/>`);

  const hoodStops = `<stop offset="0" stop-color="${C.hoodHi}"/><stop offset="0.55" stop-color="${C.hoodMid}"/><stop offset="1" stop-color="${C.hoodLo}"/>`;
  const hoodGrad = (name) => {
    d.raw(`<radialGradient id="${d.id(name)}" gradientUnits="userSpaceOnUse" cx="${f(82 + t * 12)}" cy="70" r="118">${hoodStops}</radialGradient>`);
    return d.url(name);
  };
  const hood = hoodGrad('hood');

  // ---- legs and boots
  if (p.feet) {
    for (const [i, x] of [[0, 89 + t * 8], [1, 111 + t * 8]]) {
      const dangle = p.fly * (i ? 6 : -4);
      fig.push(`<g transform="${rot(dangle, x, 160)}"><path d="M${f(x)} 150 L${f(x)} 173" stroke="${C.boot}" stroke-width="12" stroke-linecap="round"/><path d="M${f(x - 7)} 182 Q${f(x - 8)} 170 ${f(x + 1)} 170 Q${f(x + 11)} 170 ${f(x + 11)} 178 Q${f(x + 11)} 182 ${f(x + 7)} 182Z" fill="${C.boot}"/><path d="M${f(x - 2)} 174.5 Q${f(x + 2)} 173.5 ${f(x + 5)} 175" stroke="${C.bootHi}" stroke-width="1.2" fill="none" stroke-linecap="round"/></g>`);
    }
  }

  // ---- hood tip: a soft knitted tube from the crown that flops over, ending in a tassel
  const side = p.tipSide;
  const perk = p.tip; // 1 = stands up, -1 = droops
  const curl = p.tipCurl;
  const tb = [113 + t * 8, 60];
  const tc = [
    tb,
    [tb[0] + side * 10, tb[1] - 22 - perk * 8],
    [tb[0] + side * (26 - perk * 10), tb[1] - 30 - perk * 18 + curl * 6],
    [tb[0] + side * (40 - perk * 22 - curl * 8), tb[1] - 22 - perk * 30 + Math.max(0, -perk) * 34 + curl * 2 - p.fly * 0],
    [tb[0] + side * (42 - perk * 30 - curl * 22), tb[1] - 6 - perk * 40 + Math.max(0, -perk) * 50 + curl * 6],
  ];
  if (p.fly > 0) {
    tc[2] = [tb[0] - 18 * p.fly, tb[1] - 24];
    tc[3] = [tb[0] - 40 * p.fly, tb[1] - 22];
    tc[4] = [tb[0] - 58 * p.fly, tb[1] - 12];
  }
  // build the tube as an outline of varying width
  const samples = [];
  const N = 24;
  for (let i = 0; i <= N; i++) {
    const u = (i / N) * (tc.length - 1);
    const k = Math.min(tc.length - 2, Math.floor(u)), w = u - k;
    const p0 = tc[Math.max(0, k - 1)], p1 = tc[k], p2 = tc[k + 1], p3 = tc[Math.min(tc.length - 1, k + 2)];
    const cr = (a, b, c, e) => 0.5 * (2 * b + (-a + c) * w + (2 * a - 5 * b + 4 * c - e) * w * w + (-a + 3 * b - 3 * c + e) * w * w * w);
    samples.push([cr(p0[0], p1[0], p2[0], p3[0]), cr(p0[1], p1[1], p2[1], p3[1])]);
  }
  const L = [], Rr = [];
  for (let i = 0; i <= N; i++) {
    const a = samples[Math.max(0, i - 1)], b = samples[Math.min(N, i + 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
    const w = (13 * (1 - i / N) + 3.2) ;
    L.push([samples[i][0] - (dy / len) * w, samples[i][1] + (dx / len) * w]);
    Rr.push([samples[i][0] + (dy / len) * w, samples[i][1] - (dx / len) * w]);
  }
  const tubeD = 'M' + L.map((q) => `${f(q[0])} ${f(q[1])}`).join(' L') + ' L' + Rr.reverse().map((q) => `${f(q[0])} ${f(q[1])}`).join(' L') + 'Z';
  const tipEnd = samples[N];
  const tubeFill = d.linear('tube', [[0, C.hoodMid], [1, C.hoodLo]], { x1: 0, y1: 0, x2: 1, y2: 1 });
  const tube = `<path d="${tubeD}" fill="${tubeFill}" stroke="${C.hoodMid}" stroke-width="0.6" stroke-linejoin="round"/>`;
  const tubeStitch = p.small ? '' : samples.filter((_, i) => i % 3 === 1 && i < N - 2).map((q) => `<circle cx="${f(q[0])}" cy="${f(q[1])}" r="0.9" fill="${C.stitch}" opacity="0.45"/>`).join('');
  const tasselFill = d.radial('tassel', [[0, '#FFD98A'], [1, C.tasselLo]], { cx: 0.4, cy: 0.35, r: 0.7 });
  const strands = p.small ? '' : Array.from({ length: 9 }, (_, i) => {
    const a = -70 + i * 17.5;
    return `<path d="M${f(tipEnd[0])} ${f(tipEnd[1])} l${f(9.5 * sinA(a + 180))} ${f(9.5 * -cosA(a + 180))}" stroke="${C.tasselLo}" stroke-width="1.3" stroke-linecap="round"/>`;
  }).join('');
  const tassel = `${strands}<circle cx="${f(tipEnd[0])}" cy="${f(tipEnd[1])}" r="7.2" fill="${tasselFill}"/>`;
  fig.push(`<g>${tube}${tubeStitch}${tassel}</g>`);

  // ---- mittens peeking out under the cape
  const mitt = (s, a) => {
    const ax = 100 + s * 40 + t * 6, ay = 120;
    if (a <= 40) {
      const ex = 100 + s * 46 + t * 6, ey = 151;
      return `<ellipse cx="${f(ex)}" cy="${f(ey)}" rx="7" ry="6" fill="${C.mitt}"/><path d="M${f(ex - 4.5)} ${f(ey + 2)} q4.5 3 9 0" stroke="${C.mittLo}" stroke-width="1.2" fill="none"/>`;
    }
    // raised: a = angle from hanging down, toward the outside
    const ang = rad(a);
    const L = 34;
    const ex = ax + s * L * Math.sin(ang), ey = ay + L * Math.cos(ang);
    const mx = ax + s * L * 0.5 * Math.sin(ang * 0.7), my = ay + L * 0.5 * Math.cos(ang * 0.7) + 4;
    return `<path d="M${f(ax)} ${f(ay)} Q${f(mx)} ${f(my)} ${f(ex)} ${f(ey)}" stroke="${C.hoodLo}" stroke-width="12.5" fill="none" stroke-linecap="round"/><path d="M${f(ax)} ${f(ay)} Q${f(mx)} ${f(my)} ${f(ex)} ${f(ey)}" stroke="${C.hoodMid}" stroke-width="10" fill="none" stroke-linecap="round"/><circle cx="${f(ex + s * 2 * Math.sin(ang))}" cy="${f(ey + 2 * Math.cos(ang))}" r="6.6" fill="${C.mitt}"/>`;
  };
  const mittL = mitt(-1, p.armL), mittR = mitt(1, p.armR);

  // ---- the hood and capelet, one soft bell shape
  const flare = p.fly * 8;
  const hx = 100 + t * 5;
  const hem = (x) => 153 + Math.sin(x / 7) * 1.4;
  let hoodD = `M${f(42 - flare)} ${f(153)} C${f(42 - flare * 0.5)} 132 ${f(50)} 120 ${f(52)} 98 C${f(54)} 66 ${f(74 + t * 4)} 50 ${f(hx)} 50 C${f(126 + t * 4)} 50 ${f(146)} 66 ${f(148)} 98 C${f(150)} 120 ${f(158 + flare * 0.5)} 132 ${f(158 + flare)} 153`;
  const x0 = 158 + flare, x1 = 42 - flare, steps = 12, dx = (x0 - x1) / steps;
  for (let i = 0; i < steps; i++) {
    const x = x0 - i * dx;
    const yEnd = i === steps - 1 ? 153 : hem(x - dx);
    hoodD += ` Q${f(x - dx / 2)} ${f(hem(x) + 6)} ${f(x - dx)} ${f(yEnd)}`;
  }
  hoodD += 'Z';
  fig.push(`<path d="${hoodD}" fill="${hood}"/>`);
  const hoodClip = d.clip('hoodclip', `<path d="${hoodD}"/>`);
  const shade = [];
  shade.push(`<ellipse cx="100" cy="176" rx="64" ry="20" fill="#2E2463" opacity="0.32" filter="${softer}"/>`);
  shade.push(`<ellipse cx="${f(80 + t * 8)}" cy="60" rx="18" ry="8" fill="#fff" opacity="0.3" transform="${rot(-24, 80 + t * 8, 60)}" filter="${soft}"/>`);
  // shoulder line where hood meets capelet
  shade.push(`<path d="M52 128 Q100 ${f(150)} 148 128" stroke="#2E2463" stroke-width="5" fill="none" opacity="0.18" filter="${soft}"/>`);
  if (!p.small) {
    // knit stitches: rows of small v's that follow the dome
    for (let row = 0; row < 9; row++) {
      const y = 58 + row * 11;
      const half = Math.min(42, 20 + row * 7);
      for (let x = -half; x <= half; x += 7) {
        const xx = hx + x + (row % 2) * 3.5;
        shade.push(`<path d="M${f(xx - 2)} ${f(y + Math.abs(x) * 0.06)} l2 2.4 l2 -2.4" stroke="${C.stitch}" stroke-width="0.9" fill="none" opacity="0.28" stroke-linecap="round"/>`);
      }
    }
    // ribbed hem
    for (let x = 52; x <= 148; x += 5) {
      shade.push(`<path d="M${x} ${f(hem(x) - 9)} l0 8" stroke="${C.stitch}" stroke-width="1.2" opacity="0.3" stroke-linecap="round"/>`);
    }
    shade.push(`<path d="M44 ${f(143)} Q100 ${f(151)} 156 143" stroke="${C.tassel}" stroke-width="2.6" fill="none" opacity="0.85"/>`);
  } else {
    shade.push(`<path d="M44 143 Q100 151 156 143" stroke="${C.tassel}" stroke-width="3" fill="none"/>`);
  }
  fig.push(`<g clip-path="${hoodClip}">${shade.join('')}</g>`);
  d.raw(`<mask id="${d.id('rim')}" maskUnits="userSpaceOnUse" x="0" y="0" width="200" height="200"><path d="${hoodD}" fill="#fff"/><path d="${hoodD}" fill="#000" transform="translate(-4 3)" filter="${d.url('rimblur')}"/></mask>`);
  d.blur('rimblur', 1.5);
  fig.push(`<path d="${hoodD}" fill="#F1ECFF" opacity="0.5" mask="${d.url('rim')}"/>`);

  // ---- face in the hood opening
  const fcx = 100 + 40 * sinA(th) + p.gx * 3, fcy = 101 + p.gy * 2;
  const frx = 33 * (1 - Math.abs(t) * 0.22), fry = 28;
  const brimDrop = p.brim * 14;
  const face = [];
  face.push(`<ellipse cx="${f(fcx)}" cy="${f(fcy + 0.5)}" rx="${f(frx + 3)}" ry="${f(fry + 2.6)}" fill="${C.rim}"/>`);
  const faceFill = d.linear('face', [[0, C.faceHi], [1, C.faceLo]]);
  const faceClip = d.clip('faceclip', `<ellipse cx="${f(fcx)}" cy="${f(fcy + 1)}" rx="${f(frx)}" ry="${f(fry)}"/>`);
  face.push(`<ellipse cx="${f(fcx)}" cy="${f(fcy + 1)}" rx="${f(frx)}" ry="${f(fry)}" fill="${faceFill}"/>`);
  const inner = [];
  // hood shadow on the face
  inner.push(`<ellipse cx="${f(fcx)}" cy="${f(fcy - fry - 2 + brimDrop)}" rx="${f(frx + 6)}" ry="12" fill="#3B2E6E" opacity="0.32" filter="${soft}"/>`);
  if (p.blush > 0) for (const s of [-1, 1]) inner.push(`<ellipse cx="${f(fcx + s * 17)}" cy="${f(fcy + 9)}" rx="6" ry="3.4" fill="${C.blush}" opacity="${f(0.6 * p.blush)}" filter="${soft}"/>`);
  for (const sideName of ['L', 'R']) {
    const s = sideName === 'L' ? -1 : 1;
    const x = fcx + s * 13 * (1 - (s * t > 0 ? Math.abs(t) * 0.3 : 0)) + p.gx * 1.5;
    const y = fcy - 1 + p.gy * 1.5;
    const fore = 1 - (s * t > 0 ? Math.abs(t) * 0.35 : 0);
    const lid = p[`lid${sideName}`], lower = p[`lower${sideName}`], es = p[`eyeScale${sideName}`];
    const rx = 6.6, ry = 7.8;
    const yl = -ry + lid * ry * 2.1, yb = ry - lower * ry * 1.25;
    const eyeFill = d.radial(`eye${sideName}`, [[0, C.eyeHi], [1, C.eye]], { cx: 0.5, cy: 0.85, r: 0.75 });
    const clip = d.clip(`eyeclip${sideName}`, `<ellipse rx="${rx}" ry="${ry}"/>`);
    const big = d.clip(`eyebig${sideName}`, `<ellipse rx="${rx + 1.2}" ry="${ry + 1.2}"/>`);
    const ball = lid > 0.97 ? '' : `<g clip-path="${clip}"><ellipse rx="${rx}" ry="${ry}" fill="${eyeFill}"/><circle cx="${f(1.8 + p.gx * 0.6)}" cy="${f(-2 + p.gy * 0.6)}" r="2" fill="#fff"/><circle cx="-1.9" cy="2.6" r="0.8" fill="#fff" opacity="0.7"/></g>`;
    const lids = `<path d="M-8 -10 L8 -10 L8 ${f(yl)} Q0 ${f(yl + 2.6)} -8 ${f(yl)}Z" fill="${C.lid}"/>${lower > 0 ? `<path d="M-8 10 L-8 ${f(yb + 2)} Q0 ${f(yb - 4.6)} 8 ${f(yb + 2)} L8 10Z" fill="${C.lid}"/>` : ''}`;
    const closed = Math.min(yl, ry - 0.4);
    const lidLine = lid > 0.04 ? `<path d="M${-rx - 0.3} ${f(closed)} Q0 ${f(closed + 2.6)} ${rx + 0.3} ${f(closed)}" stroke="${C.lidLine}" stroke-width="${lid > 0.95 ? 1.6 : 0.9}" fill="none" stroke-linecap="round" opacity="${lid > 0.95 ? 1 : 0.55}"/>` : '';
    const lowerLine = lower > 0.3 ? `<path d="M${-rx + 0.4} ${f(yb + 2)} Q0 ${f(yb - 4.6)} ${rx - 0.4} ${f(yb + 2)}" stroke="${C.lidLine}" stroke-width="${lower > 0.7 ? 1.5 : 0.9}" fill="none" stroke-linecap="round" opacity="0.85"/>` : '';
    inner.push(`<g transform="translate(${f(x)} ${f(y)}) scale(${f(fore * es)} ${f(es)})">${ball}<g clip-path="${big}">${lids}</g>${lidLine}${lowerLine}</g>`);
    // brows: short soft strokes, only when a feeling needs them
    const raise = p[`brow${sideName}`], tilt = p[`browTilt${sideName}`];
    if (Math.abs(raise) > 0.15 || Math.abs(tilt) > 0.15) {
      const by = y - 10 - raise * 2.5;
      inner.push(`<path d="${taper([x - 4.5, by + 0.5], [x, by - 1.5], [x + 4.5, by + 0.5], 2, 1)}" fill="${C.lidLine}" opacity="0.7" transform="${rot(tilt * 18 * -s, x, by)}"/>`);
    }
  }
  // nose and mouth
  const nx = fcx + t * 6 + p.gx * 1.5, ny = fcy + 7;
  inner.push(`<path d="M${f(nx - 4)} ${f(ny - 1.6)} Q${f(nx)} ${f(ny - 3.4)} ${f(nx + 4)} ${f(ny - 1.6)} Q${f(nx + 3.4)} ${f(ny + 2.4)} ${f(nx)} ${f(ny + 3)} Q${f(nx - 3.4)} ${f(ny + 2.4)} ${f(nx - 4)} ${f(ny - 1.6)}Z" fill="${C.nose}"/><ellipse cx="${f(nx - 1.2)}" cy="${f(ny - 1.2)}" rx="1.4" ry="0.7" fill="#fff" opacity="0.55"/>`);
  const mx = fcx + t * 5 + p.gx * 1.5, my = fcy + 14;
  if (p.mouth > 0.05) inner.push(`<path d="M${f(mx - 3.8)} ${f(my)} Q${f(mx)} ${f(my - 1)} ${f(mx + 3.8)} ${f(my)} Q${f(mx + 3)} ${f(my + 2.5 + p.mouth * 5)} ${f(mx)} ${f(my + 3 + p.mouth * 5)} Q${f(mx - 3)} ${f(my + 2.5 + p.mouth * 5)} ${f(mx - 3.8)} ${f(my)}Z" fill="${C.mouth}"/>`);
  else inner.push(`<path d="M${f(mx - 3.5)} ${f(my)} Q${f(mx)} ${f(my + p.smile * 7)} ${f(mx + 3.5)} ${f(my)}" stroke="${C.mouth}" stroke-width="1.5" fill="none" stroke-linecap="round"/>`);
  // the brim pulled down over his eyes when he sleeps
  if (p.brim > 0) inner.push(`<path d="M${f(fcx - frx - 4)} ${f(fcy - fry - 6)} L${f(fcx + frx + 4)} ${f(fcy - fry - 6)} L${f(fcx + frx + 4)} ${f(fcy - fry + 4 + brimDrop)} Q${f(fcx)} ${f(fcy - fry + 12 + brimDrop * 1.5)} ${f(fcx - frx - 4)} ${f(fcy - fry + 4 + brimDrop)}Z" fill="${hood}"/>`);
  face.push(`<g clip-path="${faceClip}">${inner.join('')}</g>`);
  fig.push(`<g transform="${rot(p.headTilt, fcx, fcy + 10)}">${face.join('')}</g>`);
  fig.push(mittL, mittR);

  const transform = [`translate(0 ${f(-lift)})`, rot(p.lean, 100, GROUND), scaleAt(1 - p.squash * 0.6, 1 + p.squash, 100, GROUND)].join(' ');
  out.push(`<g transform="${transform}">${fig.join('')}</g>`);
  if (p.cursorAt) out.push(cursor(p.cursorAt[0], p.cursorAt[1], 1.1, C.mark));
  out.push(extras(p.extras, C.mark, { x: 100, y: 58 - lift }));
  return { defs: d.toString(), body: out.join('') };
}

export const states = [
  ['idle', {}],
  ['listening', { lean: -4, headTilt: -6, lid: 0.05, brow: 0.6, tip: 1, gx: -0.3 }],
  ['thinking', { gx: -0.6, gy: -0.8, lid: 0.25, browL: 0.8, browR: -0.2, headTilt: 5, tipCurl: 1, smile: 0, extras: ['think'] }],
  ['speaking', { mouth: 0.6, lid: 0.1, brow: 0.3, tip: 0.3 }],
  ['working', { turn: -0.4, gx: -0.8, gy: 0.4, lid: 0.32, brow: -0.4, browTilt: -0.4, smile: 0, armL: 70, cursorAt: [24, 112] }],
  ['flying', { turn: -0.3, fly: 1, lean: -10, gx: -0.6, lid: 0.1, brow: 0.3 }],
  ['pointing', { turn: -0.35, armL: 130, gx: -0.9, gy: -0.6, lid: 0.1, brow: 0.5, lean: -3, cursorAt: [22, 56] }],
  ['happy', { lower: 0.9, lid: 0, brow: 0.7, smile: 0.7, lift: 5, squash: 0.03, blush: 0.7, tip: 0.8 }],
  ['concerned', { lean: 5, browTilt: 1, brow: 0.2, lid: 0.05, eyeScale: 0.9, smile: -0.4, tip: -1 }],
  ['sleepy', { lid: 1, brim: 1, squash: -0.05, headTilt: -8, tip: -1, smile: 0.1, extras: ['zzz'] }],
  ['confused', { headTilt: 11, browR: 1, browL: -0.6, eyeScaleL: 0.8, lid: 0.1, smile: -0.2, tipCurl: 1.6, tip: 0.4, extras: ['question'] }],
  ['quietly proud', { lid: 0.3, lower: 1, brow: 0.5, headTilt: 6, smile: 0.6, squash: 0.035, blush: 0.6, gy: -0.3, tip: 0.6, extras: ['spark'] }],
];
