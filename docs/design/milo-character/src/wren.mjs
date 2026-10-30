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
  turn: -0.2, lean: 0, squash: 0, lift: 0, headTilt: 0,
  gx: 0, gy: 0,
  lid: 0.2, lidL: null, lidR: null, lower: 0, lowerL: null, lowerR: null,
  eyeScale: 1, eyeScaleL: null, eyeScaleR: null,
  brow: 0, browL: null, browR: null, browTilt: 0, browTiltL: null, browTiltR: null,
  mouth: 0, blush: 0,
  wingL: 0, wingR: 0, wingLenL: 1, wingLenR: 1, wingOpenL: 0, wingOpenR: 0, fly: 0,
  tail: 0, tailFan: 0,
  scarf: 0, scarfToss: 0, scarfUp: 0,
  feet: 1, pencil: 1, extras: [], cursorAt: null, small: false,
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
  const xr = 157 + Math.max(t, 0) * 5, xl = 43 + Math.min(t, 0) * 5;
  const bodyD = `M${f(100 + t * 9)} ${top} C${f(134 + t * 6)} ${top} ${f(xr)} ${f(top + 34)} ${f(xr)} 126 C${f(xr)} 160 133 180 100 180 C67 180 ${f(xl)} 160 ${f(xl)} 126 C${f(xl)} ${f(top + 34)} ${f(66 + t * 8)} ${top} ${f(100 + t * 9)} ${top}Z`;

  // The body gradient lives in figure space so lids and other body-coloured parts can reuse it and match.
  const bodyStops = [[0, C.bodyHi], [0.5, C.bodyMid], [1, C.bodyLo]];
  const bodyGrad = (name, transform = '') => {
    d.raw(`<radialGradient id="${d.id(name)}" gradientUnits="userSpaceOnUse" cx="${f(84 + t * 12)}" cy="90" r="100"${transform ? ` gradientTransform="${transform}"` : ''}>${bodyStops.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join('')}</radialGradient>`);
    return d.url(name);
  };
  const bodyFill = bodyGrad('body');
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

  // ---- tail, behind the body: one barred feather fan, cocked up past his back
  // the tail sits on the side he faces away from (right, when he faces the screen centre)
  const back = t > 0.02 ? -1 : 1;
  const tailBase = [100 + back * (26 + Math.abs(t) * 34), 146];
  const tailAngle = back * (27 + p.tail * 0.8 + Math.abs(t) * 10 + p.fly * 42); // degrees from vertical
  const tailFill = d.linear('tail', [[0, C.tail], [1, C.tailLo]]);
  const L = 74 * (1 - p.fly * 0.3);
  const w = 7.5 + Math.max(p.tailFan, p.fly) * 3.5;
  // narrow at the base, opening to three rounded feather tips
  const tip = (cx) => `Q${f(cx - w * 0.36)} ${f(-L - 3.2)} ${f(cx)} ${f(-L - 0.6)}`;
  const tailShape = `M${f(-w * 0.5)} 0 C${f(-w * 0.75)} ${f(-L * 0.45)} ${f(-w - 1.2)} ${f(-L * 0.78)} ${f(-w)} ${f(-L + 2)} ${tip(-w * 0.33)} ${tip(w * 0.33)} ${tip(w)} C${f(w + 1.2)} ${f(-L * 0.78)} ${f(w * 0.75)} ${f(-L * 0.45)} ${f(w * 0.5)} 0Z`;
  const tailBars = p.small ? '' : [0.56, 0.7, 0.84]
    .map((y) => `<path d="M${-w} ${f(-L * y + 1.8)} Q0 ${f(-L * y - 1.6)} ${w} ${f(-L * y + 1.8)}" stroke="${C.tailBar}" stroke-width="1.7" fill="none" stroke-linecap="round" opacity="0.55"/>`)
    .join('');
  const tailNotch = '';
  fig.push(`<g transform="translate(${f(tailBase[0])} ${f(tailBase[1])}) rotate(${f(tailAngle)})"><path d="${tailShape}" fill="${tailFill}"/>${tailBars}${tailNotch}<path d="M${f(-w + 2)} ${f(-L + 6)} Q0 ${f(-L - 1)} ${f(w - 3)} ${f(-L + 5)}" stroke="#fff" stroke-width="1" opacity="0.25" fill="none"/></g>`);

  // ---- wings, defined hanging from the shoulder; the far one sits behind the body
  // A folded wing hangs from the shoulder. An open wing (flying, pointing) is a broad fan whose primaries
  // spread like fingers; `wingOpen` picks it per side.
  const wing = (side) => {
    const s = side === 'L' ? -1 : 1;
    const open = Math.max(p.fly, side === 'L' ? p.wingOpenL : p.wingOpenR);
    const len = (side === 'L' ? p.wingLenL : p.wingLenR);
    const angle = side === 'L' ? p.wingL : -p.wingR;
    const x = side === 'L' ? 50 + t * 20 : 150 + t * 20;
    const y = 112;
    const fill = d.linear(`wing${side}`, [[0, C.wingHi], [1, C.wingLo]]);
    if (open > 0.5) {
      // drawn pointing straight out to the side; `angle` lifts it (positive = up)
      const k = len * 0.8;
      const q = (x0, y0) => `${f(s * x0 * k)} ${f(y0 * k)}`;
      const shape = `M${q(0, -6)} C${q(16, -16)} ${q(40, -24)} ${q(62, -20)} Q${q(68, -17)} ${q(62, -12)} Q${q(66, -8)} ${q(58, -5)} Q${q(61, 0)} ${q(52, 1)} Q${q(54, 6)} ${q(44, 6)} Q${q(44, 11)} ${q(34, 10)} C${q(22, 10)} ${q(8, 9)} ${q(0, 6)}Z`;
      const bars = p.small ? '' : [[30, -14, 32, 7], [42, -17, 44, 3], [52, -18, 53, 0]]
        .map(([a, b, c2, e]) => `<path d="M${q(a, b)} L${q(c2, e)}" stroke="${C.wingBar}" stroke-width="1.2" stroke-linecap="round" opacity="0.45"/>`)
        .join('');
      const flap = s * -(angle * 0 + (side === 'L' ? p.wingL : p.wingR));
      return `<g transform="translate(${f(x)} ${y - 4}) rotate(${f(flap)})"><path d="${shape}" fill="${fill}"/>${bars}<path d="M${q(4, -6)} C${q(18, -14)} ${q(40, -21)} ${q(60, -19)}" stroke="#fff" stroke-width="1.2" fill="none" opacity="0.3"/></g>`;
    }
    const L = 46 * len;
    const shape = `M${2 * s} -5 C${-9 * s} -5 ${-15 * s} 8 ${-15 * s} ${f(L * 0.42)} C${-15 * s} ${f(L * 0.72)} ${-9 * s} ${f(L * 0.9)} ${-4 * s} ${f(L)} C${4 * s} ${f(L * 0.82)} ${11 * s} ${f(L * 0.6)} ${11 * s} ${f(L * 0.36)} C${11 * s} 8 ${10 * s} -5 ${2 * s} -5Z`;
    const bars = p.small ? '' : [0.56, 0.7, 0.84]
      .map((k, i) => `<path d="M${f(-12 * s + i * 2.5 * s)} ${f(L * k)} Q${f(-4 * s)} ${f(L * k + 2.6)} ${f(5 * s - i * 2.5 * s)} ${f(L * k - 1.5)}" stroke="${C.wingBar}" stroke-width="1.3" fill="none" stroke-linecap="round" opacity="0.4"/>`)
      .join('');
    return `<g transform="translate(${f(x)} ${y}) rotate(${f(angle)})"><path d="${shape}" fill="${fill}"/>${bars}</g>`;
  };
  const farWing = t > 0.05 ? 'R' : t < -0.05 ? 'L' : null;
  if (farWing && (p.fly > 0.2 || p[`wingOpen${farWing}`] > 0.5)) fig.push(wing(farWing));

  // ---- body with shading
  fig.push(`<path d="${bodyD}" fill="${bodyFill}"/>`);
  const shade = [];
  // belly patch
  const bellyX = 100 + R * sinA(th * 0.75);
  const bellyFill = d.linear('belly', [[0, C.bellyHi], [1, C.bellyLo]]);
  shade.push(`<ellipse cx="${f(bellyX)}" cy="150" rx="${f(36 - Math.abs(t) * 4)}" ry="35" fill="${bellyFill}"/>`);
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
      ribs.push(`M${f(x)} ${f(yMid + 2)}l0.6 10.5`);
    }
    fig.push(`<path d="${ribs.join('')}" stroke="${C.scarfRib}" stroke-width="1.1" stroke-linecap="round" opacity="0.55"/>`);
  }
  fig.push(`<path d="M44 ${f(sy - 5)} Q100 ${f(sy + 12)} 156 ${f(sy - 5)}" stroke="#FFE2A6" stroke-width="1.4" fill="none" opacity="0.7"/></g>`);

  // knot and loose end on his front right (turns with him)
  const knotX = 100 + R * sinA(th + 32);
  const knotY = sy + 10 + (1 - ((knotX - 100) / 56) ** 2) * 2;
  const endAngle = -12 + p.scarf + p.scarfToss * -118 + p.fly * -70;
  const endLen = 38 * (1 + p.scarfToss * 0.2);
  const endShape = `M-6 0 C-7 ${endLen * 0.4} -8.5 ${endLen * 0.8} -9 ${endLen} L9 ${endLen + 2} C7.5 ${endLen * 0.7} 6.5 ${endLen * 0.35} 6 0Z`;
  const fringe = p.small ? '' : [-7, -3.5, 0, 3.5, 7]
    .map((x) => `<path d="M${x} ${endLen + 1 + x * 0.1} l${x * 0.08} 5" stroke="${C.scarfLo}" stroke-width="1.7" stroke-linecap="round"/>`)
    .join('');
  const endRibs = p.small ? '' : `<path d="M-2 5 L-3 ${endLen - 2} M2.5 5 L3 ${endLen - 1}" stroke="${C.scarfRib}" stroke-width="1" opacity="0.5"/>`;
  const scarfEnd = `<g transform="translate(${f(knotX)} ${f(knotY)}) rotate(${f(endAngle)})"><path d="${endShape}" fill="${scarfFill}"/>${endRibs}${fringe}<path d="M-6 0 L6 0" stroke="#2E2463" stroke-width="2" opacity="0.18"/></g>`;
  const knot = `<ellipse cx="${f(knotX)}" cy="${f(knotY)}" rx="8" ry="6.5" fill="${scarfFill}"/><path d="M${f(knotX - 5)} ${f(knotY - 1)} q5 3 10 0" stroke="${C.scarfLo}" stroke-width="1.2" fill="none" opacity="0.7"/>`;

  // ---- near wing over the body
  if (farWing !== 'L' || Math.abs(t) < 0.25) fig.push(wing('L'));
  if (farWing !== 'R' || Math.abs(t) < 0.25) fig.push(wing('R'));

  // the loose end hangs over the wing unless it is tossed back
  // tossed over his shoulder it still lies in front, across the near shoulder
  fig.push(scarfEnd);
  fig.push(knot);
  if (p.pencil && !p.small) {
    const px = 100 + R * sinA(th - 24), py = sy + 7;
    fig.push(`<g transform="translate(${f(px)} ${f(py)}) rotate(-24)"><rect x="-2.6" y="-22" width="5.2" height="25" rx="1" fill="#4B3D86"/><rect x="-2.6" y="-22" width="1.8" height="25" fill="#6F61B4"/><rect x="-2.6" y="-25.5" width="5.2" height="4" rx="1.2" fill="#E89AA6"/><rect x="-2.6" y="-22.4" width="5.2" height="1.4" fill="#C9C2D8"/></g>`);
    // the scarf band passes over the pencil's lower half
    fig.push(`<g clip-path="${bodyClip}"><path d="${band}" fill="${scarfFill}" clip-path="${d.clip('pencilband', `<rect x="${f(px - 9)}" y="${f(sy - 6)}" width="18" height="30"/>`)}"/></g>`);
  }

  // ---- rim light: a soft crescent on the side away from the key light
  d.raw(`<mask id="${d.id('rim')}" maskUnits="userSpaceOnUse" x="0" y="0" width="200" height="200"><path d="${bodyD}" fill="#fff"/><path d="${bodyD}" fill="#000" transform="translate(-5 3.5)" filter="${d.url('rimblur')}"/></mask>`);
  d.blur('rimblur', 1.6);
  fig.push(`<path d="${bodyD}" fill="#F1ECFF" opacity="0.55" mask="${d.url('rim')}"/>`);

  // ---- face
  const face = [];
  const fx = (a) => 100 + R * sinA(a);
  const gx = p.gx * 4.5, gy = p.gy * 3.5;
  const eyeY = 99 + gy - p.scarfUp * 4;
  const eyes = [
    { side: 'L', a: th - 23 },
    { side: 'R', a: th + 23 },
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
    const rx = 7.4, ry = 8.8;
    const yl = -ry + lid * ry * 2.1;
    const sag = -1.6 + 5 * lid * lid; // how much the lid edge dips in the middle
    const yb = ry - lower * ry * 1.25;
    const eyeFill = d.radial(`eye${e.side}`, [[0, C.eyeHi], [1, C.eye]], { cx: 0.5, cy: 0.85, r: 0.75 });
    const clip = d.clip(`eyeclip${e.side}`, `<ellipse cx="0" cy="0" rx="${rx}" ry="${ry}"/>`);
    const parts = [];
    const lidFill = bodyGrad(`lid${e.side}`, `scale(${f(1 / (fore * es))} ${f(1 / es)}) translate(${f(-x)} ${f(-eyeY)})`);
    parts.push(`<ellipse cx="0" cy="0" rx="${rx}" ry="${ry}" fill="${eyeFill}"/>`);
    parts.push(`<circle cx="${f(2.4 + p.gx * 0.7)}" cy="${f(-2.6 + p.gy * 0.6)}" r="2.6" fill="#fff"/>`);
    parts.push(`<circle cx="-2.6" cy="3.3" r="1.1" fill="#fff" opacity="0.75"/>`);
    // upper lid with the soft shadow it casts, and the lower lid that pushes up into a smile. Both sit
    // outside the eye's clip, on a slightly larger clip, so no dark fringe shows around a closed eye.
    const lids = [];
    lids.push(`<path d="M-11 -12 L11 -12 L11 ${f(yl)} Q0 ${f(yl + sag)} -11 ${f(yl)}Z" fill="#1B1430" opacity="0.3" transform="translate(0 1.6)" clip-path="${clip}"/>`);
    lids.push(`<path d="M-11 -12 L11 -12 L11 ${f(yl)} Q0 ${f(yl + sag)} -11 ${f(yl)}Z" fill="${lidFill}"/>`);
    if (lower > 0) lids.push(`<path d="M-11 12 L-11 ${f(yb + 3)} Q0 ${f(yb - 6)} 11 ${f(yb + 3)} L11 12Z" fill="${lidFill}"/>`);
    const big = d.clip(`eyebig${e.side}`, `<ellipse cx="0" cy="0" rx="${rx + 1.2}" ry="${ry + 1.2}"/>`);
    const closed = Math.min(yl, ry - 0.5);
    const lidLine = lid > 0.04 ? `<path d="M${-rx - 0.4} ${f(closed)} Q0 ${f(closed + sag)} ${rx + 0.4} ${f(closed)}" stroke="${C.lidLine}" stroke-width="${lid > 0.95 ? 2.1 : 1.1}" fill="none" stroke-linecap="round" opacity="${lid > 0.95 ? 1 : 0.6}"/>` : '';
    const lowerLine = lower > 0.3 ? `<path d="M${-rx + 0.5} ${f(yb + 2.6)} Q0 ${f(yb - 5.6)} ${rx - 0.5} ${f(yb + 2.6)}" stroke="${C.lidLine}" stroke-width="${lower > 0.7 ? 1.8 : 1}" fill="none" stroke-linecap="round" opacity="${lower > 0.7 ? 0.9 : 0.5}"/>` : '';
    const eyeBall = lid > 0.97 ? '' : `<g clip-path="${clip}">${parts.join('')}</g>`;
    if (lower > 0.8) {
      face.push(`<g transform="translate(${f(x)} ${f(eyeY + 2)}) scale(${f(fore * es)} ${f(es)})"><path d="M-6.8 2.6 Q0 -7.4 6.8 2.6" stroke="${C.eye}" stroke-width="3" fill="none" stroke-linecap="round"/></g>`);
    } else face.push(`<g transform="translate(${f(x)} ${f(eyeY)}) scale(${f(fore * es)} ${f(es)})">${eyeBall}<g clip-path="${big}">${lids.join('')}</g>${lidLine}${lowerLine}</g>`);

    // brow stripe: a pale sweep over the eye, running back toward the side of the head
    const raise = p[`brow${e.side}`] * 4.5;
    const tiltDeg = p[`browTilt${e.side}`] * 16 * s;
    const bx = x, by = eyeY - 13.5 - raise;
    const inner = [bx - s * 8 * fore, by + 2.5];
    const outer = [bx + s * 18 * fore, by + 6];
    const mid = [bx + s * 3 * fore, by - 4.5];
    face.push(`<path d="${taper(inner, mid, outer, 5.4, 1.4)}" fill="${C.brow}" opacity="0.96" transform="${rot(tiltDeg, bx, by)}"/>`);
  }
  // beak: thin and a touch long, the tip swings toward the turn
  const bx = fx(th) + gx * 1.1, by = 109 + gy - p.scarfUp * 6;
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
  ['listening', { lean: -4, headTilt: -7, lid: 0.1, brow: 0.5, tail: 10, gx: -0.3 }],
  ['thinking', { gx: -0.6, gy: -0.8, lid: 0.3, browL: 0.9, browR: -0.1, headTilt: 5, tail: -6, extras: ['think'] }],
  ['speaking', { mouth: 0.7, lid: 0.16, brow: 0.3, tail: 4 }],
  ['working', { turn: -0.45, gx: -0.8, gy: 0.4, lid: 0.36, brow: -0.3, browTilt: -0.3, scarfToss: 1, cursorAt: [26, 128] }],
  ['flying', { turn: -0.3, fly: 1, lean: -8, wingL: 45, wingR: 45, wingLenL: 0.95, wingLenR: 0.95, gx: -0.6, lid: 0.16, feet: 0 }],
  ['pointing', { turn: -0.35, wingOpenL: 1, wingL: 40, wingLenL: 0.9, gx: -0.9, gy: -0.6, lid: 0.16, brow: 0.3, lean: -3, cursorAt: [16, 56] }],
  ['happy', { lower: 0.9, lid: 0, brow: 0.6, tail: 18, tailFan: 1, wingL: 14, wingR: 14, lift: 5, squash: 0.03, blush: 0.6 }],
  ['concerned', { lean: 5, browTilt: 0.9, brow: 0.3, lid: 0.1, eyeScale: 0.92, tail: -14, wingL: -4, wingR: -4, gy: 0.2 }],
  ['sleepy', { lid: 1, scarfUp: 1, squash: -0.05, tail: -22, headTilt: -8, turn: -0.1, extras: ['zzz'] }],
  ['confused', { headTilt: 11, browR: 0.9, browL: -0.4, eyeScaleL: 0.8, lid: 0.16, tail: -4, gx: 0.2, extras: ['question'] }],
  ['quietly proud', { lid: 0.3, lower: 1, brow: 0.4, headTilt: 6, tail: 20, tailFan: 0.8, squash: 0.035, blush: 0.4, gy: -0.3, extras: ['spark'] }],
];
