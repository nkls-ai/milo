// Concept A: Milo the wren. A round lavender wren with a cocked tail, pale brow stripes that work as
// eyebrows, and a marigold knitted scarf with one loose end.
import { Defs, GROUND, blob, curve, extras, f, pose as mergePose, rad, rot, scaleAt, taper, cursor } from './lib.mjs';

export const name = 'Wren';

export const C = {
  bodyHi: '#C6BCF0', bodyMid: '#9688D6', bodyLo: '#5E4FA4', lid: '#9D90DA', lidLine: '#3F3373',
  bellyHi: '#FBF3E8', bellyLo: '#E9D5C0', speck: '#CDB49C',
  brow: '#F6F2FE',
  wingHi: '#8A7CCB', wingLo: '#54468F', wingBar: '#B9AEEA',
  tail: '#6C5DB2', tailLo: '#4C3F8A', tailBar: '#43377D',
  eye: '#1E1730', eyeHi: '#4F4276',
  beakHi: '#E6B274', beakLo: '#B27744', mouth: '#6E2F3C',
  scarfHi: '#F0B649', scarfLo: '#C98526', scarfRib: '#FAD58A',
  feet: '#B17C50', blush: '#EE9AA6', mark: '#7C6CD0',
};

export const defaults = {
  turn: 0.18, lean: 0, squash: 0, lift: 0, headTilt: 0,
  gx: 0, gy: 0,
  lid: 0.26, lidL: null, lidR: null, lower: 0, lowerL: null, lowerR: null,
  eyeScale: 1, eyeScaleL: null, eyeScaleR: null,
  brow: 0, browL: null, browR: null, browTilt: 0, browTiltL: null, browTiltR: null,
  mouth: 0, blush: 0,
  wingL: 0, wingR: 0, wingLenL: 1, wingLenR: 1, fly: 0,
  tail: 0, tailFan: 0,
  scarf: 0, scarfToss: 0, scarfUp: 0,
  feet: 1, extras: [], cursorAt: null, small: false,
};

export function draw(input, uid) {
  const p = mergePose(defaults, input);
  const d = new Defs(uid);
  const t = p.turn;
  const th = t * 50; // degrees the face turns
  const R = 52;
  const sinA = (a) => Math.sin(rad(a));
  const cosA = (a) => Math.cos(rad(a));

  // ---- body silhouette: a round wren, widest a little below the middle, head slightly leading the turn
  const top = 58 + p.scarfUp * 2;
  const bodyD = `M${f(100 + t * 5)} ${top} C${f(133 + t * 4)} ${top} 157 ${f(top + 34)} 157 ${f(126)} C157 ${f(160)} 133 180 100 180 C67 180 43 160 43 126 C43 ${f(top + 34)} ${f(67 + t * 4)} ${top} ${f(100 + t * 5)} ${top}Z`;

  const bodyFill = d.radial('body', [[0, C.bodyHi], [0.5, C.bodyMid], [1, C.bodyLo]], { cx: 0.36 + t * 0.1, cy: 0.26, r: 0.85 });
  const rim = d.linear('rim', [[0, '#fff', 0], [0.62, '#fff', 0], [1, '#EFEAFF', 0.85]], { x1: 0, y1: 0.2, x2: 1, y2: 0.6 });
  const bodyClip = d.clip('bodyclip', `<path d="${bodyD}"/>`);
  const soft = d.blur('soft', 2.2);
  const softer = d.blur('softer', 6);
  const ground = d.blur('ground', 2.6);

  const out = [];

  // ---- ground shadow (doesn't lean or lift)
  const lift = p.lift + p.fly * 16;
  const shadowScale = Math.max(0.35, 1 - lift / 70);
  out.push(`<ellipse cx="100" cy="${GROUND + 1}" rx="${f(42 * shadowScale)}" ry="${f(5.5 * shadowScale)}" fill="#2A2050" opacity="${f(0.22 * shadowScale)}" filter="${ground}"/>`);

  const fig = [];

  // ---- tail, behind the body: three barred feathers cocked up behind his back
  const tailBase = [100 - 36 - t * 30, 150];
  const tailAngle = -38 - p.tail - t * 18 + p.fly * -48; // degrees from vertical, negative leans left
  const tailFill = d.linear('tail', [[0, C.tail], [1, C.tailLo]], { x1: 0, y1: 0, x2: 0, y2: 1 });
  const feathers = [];
  const spread = 9 + p.tailFan * 8;
  for (const [i, k] of [[-1, 0.92], [1, 0.96], [0, 1]]) {
    const L = 56 * k * (1 - p.fly * 0.1);
    const a = tailAngle + i * spread;
    const shape = `M-5.5 0 C-6.5 ${f(-L * 0.5)} -7.5 ${f(-L + 7)} -1.5 ${f(-L)} C4.5 ${f(-L + 4)} 6.5 ${f(-L * 0.5)} 5.5 0Z`;
    const bars = [0.5, 0.66, 0.82]
      .map((y) => `<path d="M-6 ${f(-L * y + 1.5)} Q0 ${f(-L * y - 1.2)} 6 ${f(-L * y + 1.5)}" stroke="${C.tailBar}" stroke-width="${p.small ? 0 : 1.6}" fill="none" stroke-linecap="round" opacity="0.75"/>`)
      .join('');
    feathers.push(`<g transform="translate(${f(tailBase[0])} ${f(tailBase[1])}) rotate(${f(a)})"><path d="${shape}" fill="${tailFill}"/>${bars}<path d="M0 -4 L0 ${f(-L + 6)}" stroke="${C.wingBar}" stroke-width="0.8" opacity="0.35"/></g>`);
  }
  fig.push(`<g>${feathers.join('')}</g>`);

  // ---- wings, defined hanging from the shoulder; the far one sits behind the body
  const wing = (side) => {
    const s = side === 'L' ? -1 : 1;
    const len = (side === 'L' ? p.wingLenL : p.wingLenR) * (1 + p.fly * 0.35);
    const flyAngle = p.fly * (side === 'L' ? 112 : -112);
    const angle = (side === 'L' ? p.wingL : -p.wingR) + flyAngle;
    const x = side === 'L' ? 49 + t * 22 : 151 + t * 8;
    const y = 112;
    const L = 46 * len;
    const shape = `M${2 * s} -5 C${-9 * s} -5 ${-15 * s} 8 ${-15 * s} ${f(L * 0.42)} C${-15 * s} ${f(L * 0.72)} ${-9 * s} ${f(L * 0.9)} ${-4 * s} ${f(L)} C${4 * s} ${f(L * 0.82)} ${11 * s} ${f(L * 0.6)} ${11 * s} ${f(L * 0.36)} C${11 * s} 8 ${10 * s} -5 ${2 * s} -5Z`;
    const fill = d.linear(`wing${side}`, [[0, C.wingHi], [1, C.wingLo]]);
    const bars = p.small ? '' : [0.56, 0.7, 0.84]
      .map((k, i) => `<path d="M${f(-11 * s + i * 2 * s)} ${f(L * k)} Q${f(-3 * s)} ${f(L * k + 3)} ${f(6 * s - i * 2 * s)} ${f(L * k - 2)}" stroke="${C.wingBar}" stroke-width="1.5" fill="none" stroke-linecap="round" opacity="0.55"/>`)
      .join('');
    return `<g transform="translate(${f(x)} ${y}) rotate(${f(angle)})"><path d="${shape}" fill="${fill}"/>${bars}</g>`;
  };
  const farWing = t > 0.05 ? 'R' : t < -0.05 ? 'L' : null;
  if (farWing) fig.push(wing(farWing));

  // ---- body with shading
  fig.push(`<path d="${bodyD}" fill="${bodyFill}"/>`);
  const shade = [];
  // belly patch
  const bellyX = 100 + R * sinA(th * 0.75);
  const bellyFill = d.linear('belly', [[0, C.bellyHi], [1, C.bellyLo]]);
  shade.push(`<ellipse cx="${f(bellyX)}" cy="150" rx="${f(36 - Math.abs(t) * 4)}" ry="35" fill="${bellyFill}"/>`);
  if (!p.small) {
    for (const [dx, dy] of [[-12, 146], [6, 152], [-3, 162], [14, 163], [-17, 160]]) {
      shade.push(`<path d="M${f(bellyX + dx - 2.4)} ${dy} q2.4 2.6 4.8 0" stroke="${C.speck}" stroke-width="1.1" fill="none" stroke-linecap="round" opacity="0.8"/>`);
    }
  }
  // ambient occlusion at the bottom and a top highlight
  shade.push(`<ellipse cx="100" cy="186" rx="64" ry="22" fill="#2E2463" opacity="0.32" filter="${softer}"/>`);
  shade.push(`<ellipse cx="${f(78 + t * 8)}" cy="${top + 16}" rx="20" ry="9" fill="#fff" opacity="0.28" transform="${rot(-24, 78 + t * 8, top + 16)}" filter="${soft}"/>`);
  fig.push(`<g clip-path="${bodyClip}">${shade.join('')}</g>`);

  // ---- scarf: a knitted band, its shadow on the body, a knot and one loose end
  const sy = 121 - p.scarfUp * 8;
  const band = `M44 ${f(sy - 5)} Q100 ${f(sy + 12)} 156 ${f(sy - 5)} L157 ${f(sy + 8)} Q100 ${f(sy + 26)} 43 ${f(sy + 8)}Z`;
  fig.push(`<g clip-path="${bodyClip}"><path d="${band}" transform="translate(0 4)" fill="#2E2463" opacity="0.35" filter="${soft}"/></g>`);
  const scarfFill = d.linear('scarf', [[0, C.scarfHi], [1, C.scarfLo]]);
  fig.push(`<g clip-path="${bodyClip}"><path d="${band}" fill="${scarfFill}"/>`);
  if (!p.small) {
    const ribs = [];
    for (let i = 0; i <= 14; i++) {
      const x = 50 + i * 7.2;
      const yMid = sy - 5 + (1 - ((x - 100) / 56) ** 2) * 8.5;
      ribs.push(`<path d="M${f(x)} ${f(yMid + 2)} l0.6 ${f(10.5)}" stroke="${C.scarfRib}" stroke-width="1.1" stroke-linecap="round" opacity="0.55"/>`);
    }
    fig.push(ribs.join(''));
  }
  fig.push(`<path d="M44 ${f(sy - 5)} Q100 ${f(sy + 12)} 156 ${f(sy - 5)}" stroke="#FFE2A6" stroke-width="1.4" fill="none" opacity="0.7"/></g>`);

  // knot and loose end on his front right (turns with him)
  const knotX = 100 + R * sinA(th + 32);
  const knotY = sy + 10 + (1 - ((knotX - 100) / 56) ** 2) * 2;
  const endAngle = p.scarf * 1 + p.scarfToss * -150 + p.fly * -70;
  const endLen = 38;
  const endShape = `M-6 0 C-7 ${endLen * 0.4} -8.5 ${endLen * 0.8} -9 ${endLen} L9 ${endLen + 2} C7.5 ${endLen * 0.7} 6.5 ${endLen * 0.35} 6 0Z`;
  const fringe = p.small ? '' : [-7, -3.5, 0, 3.5, 7]
    .map((x) => `<path d="M${x} ${endLen + 1 + x * 0.1} l${x * 0.08} 5" stroke="${C.scarfLo}" stroke-width="1.7" stroke-linecap="round"/>`)
    .join('');
  const endRibs = p.small ? '' : `<path d="M-2 5 L-3 ${endLen - 2} M2.5 5 L3 ${endLen - 1}" stroke="${C.scarfRib}" stroke-width="1" opacity="0.5"/>`;
  const scarfEnd = `<g transform="translate(${f(knotX)} ${f(knotY)}) rotate(${f(endAngle)})"><path d="${endShape}" fill="${scarfFill}"/>${endRibs}${fringe}<path d="M-6 0 L6 0" stroke="#2E2463" stroke-width="2" opacity="0.18"/></g>`;
  const knot = `<ellipse cx="${f(knotX)}" cy="${f(knotY)}" rx="8" ry="6.5" fill="${scarfFill}"/><path d="M${f(knotX - 5)} ${f(knotY - 1)} q5 3 10 0" stroke="${C.scarfLo}" stroke-width="1.2" fill="none" opacity="0.7"/>`;

  // ---- near wing over the body
  if (farWing !== 'L') fig.push(wing('L'));
  if (farWing !== 'R') fig.push(wing('R'));

  // the loose end hangs over the wing unless it is tossed back
  if (p.scarfToss > 0.5) fig.splice(1, 0, scarfEnd);
  else fig.push(scarfEnd);
  fig.push(knot);

  // ---- rim light on the whole silhouette
  fig.push(`<path d="${bodyD}" fill="none" stroke="${rim}" stroke-width="3" clip-path="${bodyClip}"/>`);

  // ---- face
  const face = [];
  const fx = (a) => 100 + R * sinA(a);
  const gx = p.gx * 4.5, gy = p.gy * 3.5;
  const eyeY = 101 + gy - p.scarfUp * 4;
  const eyes = [
    { side: 'L', a: th - 21 },
    { side: 'R', a: th + 21 },
  ];
  // blush
  if (p.blush > 0) {
    for (const e of eyes) {
      face.push(`<ellipse cx="${f(fx(e.a + (e.side === 'L' ? -9 : 9)) + gx)}" cy="${f(eyeY + 13)}" rx="${f(7 * cosA(e.a))}" ry="3.6" fill="${C.blush}" opacity="${f(0.55 * p.blush)}" filter="${soft}"/>`);
    }
  }
  for (const e of eyes) {
    const s = e.side === 'L' ? -1 : 1;
    const x = fx(e.a) + gx;
    const fore = Math.max(0.35, cosA(e.a));
    const lid = p[`lid${e.side}`], lower = p[`lower${e.side}`], es = p[`eyeScale${e.side}`];
    const rx = 6.3, ry = 7.4;
    const yl = -ry + lid * ry * 2.1;
    const yb = ry - lower * ry * 1.5;
    const eyeFill = d.radial(`eye${e.side}`, [[0, C.eyeHi], [1, C.eye]], { cx: 0.5, cy: 0.85, r: 0.75 });
    const clip = d.clip(`eyeclip${e.side}`, `<ellipse cx="0" cy="0" rx="${rx}" ry="${ry}"/>`);
    const parts = [];
    parts.push(`<ellipse cx="0" cy="0" rx="${rx}" ry="${ry}" fill="${eyeFill}"/>`);
    parts.push(`<circle cx="${f(2.1 + p.gx * 0.6)}" cy="${f(-2.6 + p.gy * 0.5)}" r="2.2" fill="#fff"/>`);
    parts.push(`<circle cx="-2.2" cy="2.8" r="0.95" fill="#fff" opacity="0.8"/>`);
    // upper lid, with a soft shadow it casts on the eye
    parts.push(`<path d="M-9 -10 L9 -10 L9 ${f(yl)} Q0 ${f(yl + 3.4)} -9 ${f(yl)}Z" fill="#1B1430" opacity="0.35" transform="translate(0 1.4)"/>`);
    parts.push(`<path d="M-9 -10 L9 -10 L9 ${f(yl)} Q0 ${f(yl + 3.4)} -9 ${f(yl)}Z" fill="${C.lid}"/>`);
    // lower lid: pushes up into a smile
    if (lower > 0) parts.push(`<path d="M-9 10 L-9 ${f(yb + 2)} Q0 ${f(yb - 4.5)} 9 ${f(yb + 2)} L9 10Z" fill="${C.lid}"/>`);
    const lidLine = lid > 0.04 ? `<path d="M${-rx - 0.4} ${f(Math.min(yl, ry - 0.5))} Q0 ${f(Math.min(yl, ry - 0.5) + 3.4)} ${rx + 0.4} ${f(Math.min(yl, ry - 0.5))}" stroke="${C.lidLine}" stroke-width="${lid > 0.95 ? 1.9 : 1.3}" fill="none" stroke-linecap="round"/>` : '';
    const lowerLine = lower > 0.3 ? `<path d="M${-rx} ${f(yb + 2)} Q0 ${f(yb - 4.5)} ${rx} ${f(yb + 2)}" stroke="${C.lidLine}" stroke-width="1" fill="none" opacity="0.5"/>` : '';
    face.push(`<g transform="translate(${f(x)} ${f(eyeY)}) scale(${f(fore * es)} ${f(es)})"><g clip-path="${clip}">${parts.join('')}</g>${lidLine}${lowerLine}</g>`);

    // brow stripe: a pale sweep over the eye, running back toward the side of the head
    const raise = p[`brow${e.side}`] * 4.5;
    const tiltDeg = p[`browTilt${e.side}`] * 16 * -s;
    const bx = x, by = eyeY - 12 - raise;
    const inner = [bx - s * 7 * fore, by + 2];
    const outer = [bx + s * 15 * fore, by + 4];
    const mid = [bx + s * 3 * fore, by - 4.5];
    face.push(`<path d="${taper(inner, mid, outer, 4.6, 1.2)}" fill="${C.brow}" transform="${rot(tiltDeg, bx, by)}"/>`);
  }
  // beak: thin and a touch long, the tip swings toward the turn
  const bx = fx(th) + gx * 1.1, by = 108 + gy - p.scarfUp * 6;
  const tipX = bx + t * 9 + p.gx * 2;
  const open = p.mouth;
  const beakFill = d.linear('beak', [[0, C.beakHi], [1, C.beakLo]]);
  const lower = `<g transform="${rot(open * 26 * (t >= 0 ? 1 : -1) * 0 + 0, bx, by)}"><path d="M${f(bx - 4.5)} ${f(by + 2 + open * 4)} Q${f(bx)} ${f(by + 1 + open * 4)} ${f(bx + 4.5)} ${f(by + 2 + open * 4)} Q${f(tipX)} ${f(by + 9 + open * 7)} ${f(tipX - 0.5)} ${f(by + 10 + open * 7)} Q${f(bx - 2)} ${f(by + 7 + open * 5)} ${f(bx - 4.5)} ${f(by + 2 + open * 4)}Z" fill="${C.beakLo}"/></g>`;
  if (open > 0.05) {
    face.push(`<path d="M${f(bx - 5)} ${f(by + 1)} Q${f(bx)} ${f(by + 2 + open * 9)} ${f(bx + 5)} ${f(by + 1)} Z" fill="${C.mouth}"/>`);
  }
  face.push(lower);
  face.push(`<path d="M${f(bx - 6.5)} ${f(by)} Q${f(bx)} ${f(by - 4.5)} ${f(bx + 6.5)} ${f(by)} Q${f(bx + 3 + t * 3)} ${f(by + 6)} ${f(tipX)} ${f(by + 13)} Q${f(bx - 3 + t * 3)} ${f(by + 6)} ${f(bx - 6.5)} ${f(by)}Z" fill="${beakFill}"/>`);
  face.push(`<path d="M${f(bx - 3)} ${f(by - 1.2)} Q${f(bx)} ${f(by - 2.6)} ${f(bx + 2.5)} ${f(by - 1.4)}" stroke="#fff" stroke-width="1" opacity="0.5" fill="none" stroke-linecap="round"/>`);

  fig.push(`<g transform="${rot(p.headTilt, bx, 104)}">${face.join('')}</g>`);

  // ---- feet
  if (p.feet > 0 && p.fly < 0.5) {
    const feet = [];
    for (const x of [87 + t * 8, 113 + t * 8]) {
      feet.push(`<path d="M${f(x)} 174 L${f(x)} 181 M${f(x - 5)} 182 L${f(x)} 180.5 L${f(x + 5.5)} 182 M${f(x)} 180.5 L${f(x + 1.4)} 182.6" stroke="${C.feet}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/>`);
    }
    out.push(...[]);
    fig.unshift(feet.join(''));
  }

  const transform = [
    `translate(0 ${f(-lift)})`,
    rot(p.lean, 100, GROUND),
    scaleAt(1 - p.squash * 0.6, 1 + p.squash, 100, GROUND),
  ].join(' ');
  out.push(`<g transform="${transform}">${fig.join('')}</g>`);
  if (p.cursorAt) out.push(cursor(p.cursorAt[0], p.cursorAt[1], 1.1, C.mark));
  out.push(extras(p.extras, C.mark, { x: 100, y: 62 - lift }));
  return { defs: d.toString(), body: out.join('') };
}

/// The poses for the sheet. Each is a set of parameters on the same rig.
export const states = [
  ['idle', {}],
  ['listening', { lean: 4, headTilt: 7, lid: 0.12, brow: 0.5, tail: 10, gx: 0.3 }],
  ['thinking', { gx: 0.7, gy: -0.8, lid: 0.3, browR: 0.9, browL: -0.1, headTilt: -5, tail: -6, extras: ['think'] }],
  ['speaking', { mouth: 0.7, lid: 0.2, brow: 0.3, tail: 4 }],
  ['working', { turn: 0.45, gx: 0.8, gy: 0.4, lid: 0.38, brow: -0.3, browTilt: -0.3, scarfToss: 1, cursorAt: [160, 128] }],
  ['flying', { turn: 0.55, fly: 1, lean: 16, gx: 0.6, lid: 0.18, scarf: 0, feet: 0 }],
  ['pointing', { turn: -0.35, wingL: 128, wingLenL: 1.15, gx: -0.9, gy: -0.6, lid: 0.2, brow: 0.3, lean: -4, cursorAt: [18, 54] }],
  ['happy', { lower: 0.75, lid: 0.12, brow: 0.6, tail: 18, tailFan: 1, wingL: 14, wingR: 14, lift: 5, squash: 0.03, blush: 0.6 }],
  ['concerned', { lean: -5, browTilt: 0.9, brow: 0.3, lid: 0.12, eyeScale: 0.92, tail: -14, wingL: -4, wingR: -4, gy: 0.2 }],
  ['sleepy', { lid: 1, scarfUp: 1, squash: -0.05, tail: -22, headTilt: 8, turn: 0.1, extras: ['zzz'], feet: 1 }],
  ['confused', { headTilt: -11, browL: 0.9, browR: -0.4, eyeScaleR: 0.8, lid: 0.18, tail: -4, gx: -0.2, extras: ['question'] }],
  ['quietly proud', { lid: 1, lower: 0, brow: 0.4, headTilt: -6, tail: 20, tailFan: 0.8, squash: 0.035, blush: 0.4, gy: -0.3, extras: ['spark'] }],
];
