// Small helpers shared by the three concept rigs. Every figure draws in a 200 x 200 box with the
// ground at y = 182, so the sheets can place them at any size.

export const GROUND = 182;

export const f = (n) => Math.round(n * 100) / 100;
export const rad = (d) => (d * Math.PI) / 180;
export const lerp = (a, b, t) => a + (b - a) * t;
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export function rotPt([x, y], deg, [cx, cy]) {
  const a = rad(deg);
  const dx = x - cx, dy = y - cy;
  return [cx + dx * Math.cos(a) - dy * Math.sin(a), cy + dx * Math.sin(a) + dy * Math.cos(a)];
}

export const rot = (deg, cx, cy) => `rotate(${f(deg)} ${f(cx)} ${f(cy)})`;

/// Scale around a point (squash and stretch around the feet).
export const scaleAt = (sx, sy, cx, cy) =>
  `translate(${f(cx)} ${f(cy)}) scale(${f(sx)} ${f(sy)}) translate(${f(-cx)} ${f(-cy)})`;

/// A path from a list of commands with numbers rounded: P`M ${x} ${y}` style is overkill, so this
/// just tidies a string.
export const P = (s) => s.replace(/-?\d+\.\d{3,}/g, (m) => String(f(parseFloat(m))));

/// A gradient-and-filter registry so ids stay unique when many figures share a page.
export class Defs {
  constructor(uid) {
    this.uid = uid;
    this.items = [];
  }
  id(name) {
    return `${this.uid}-${name}`;
  }
  url(name) {
    return `url(#${this.id(name)})`;
  }
  linear(name, stops, { x1 = 0, y1 = 0, x2 = 0, y2 = 1, units = 'objectBoundingBox' } = {}) {
    this.items.push(
      `<linearGradient id="${this.id(name)}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" gradientUnits="${units}">${stopTags(stops)}</linearGradient>`
    );
    return this.url(name);
  }
  radial(name, stops, { cx = 0.5, cy = 0.5, r = 0.5, fx, fy, units = 'objectBoundingBox' } = {}) {
    const focal = fx !== undefined ? ` fx="${fx}" fy="${fy}"` : '';
    this.items.push(
      `<radialGradient id="${this.id(name)}" cx="${cx}" cy="${cy}" r="${r}"${focal} gradientUnits="${units}">${stopTags(stops)}</radialGradient>`
    );
    return this.url(name);
  }
  blur(name, sd) {
    this.items.push(
      `<filter id="${this.id(name)}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${sd}"/></filter>`
    );
    return this.url(name);
  }
  clip(name, inner) {
    this.items.push(`<clipPath id="${this.id(name)}">${inner}</clipPath>`);
    return this.url(name);
  }
  raw(s) {
    this.items.push(s);
  }
  toString() {
    return `<defs>${this.items.join('')}</defs>`;
  }
}

function stopTags(stops) {
  return stops
    .map(([o, c, a = 1]) => `<stop offset="${o}" stop-color="${c}"${a !== 1 ? ` stop-opacity="${a}"` : ''}/>`)
    .join('');
}

/// A smooth closed blob through points (Catmull-Rom to Bezier).
export function blob(points, tension = 1) {
  const n = points.length;
  let d = `M${f(points[0][0])} ${f(points[0][1])}`;
  for (let i = 0; i < n; i++) {
    const p0 = points[(i - 1 + n) % n], p1 = points[i], p2 = points[(i + 1) % n], p3 = points[(i + 2) % n];
    const c1 = [p1[0] + ((p2[0] - p0[0]) / 6) * tension, p1[1] + ((p2[1] - p0[1]) / 6) * tension];
    const c2 = [p2[0] - ((p3[0] - p1[0]) / 6) * tension, p2[1] - ((p3[1] - p1[1]) / 6) * tension];
    d += ` C${f(c1[0])} ${f(c1[1])} ${f(c2[0])} ${f(c2[1])} ${f(p2[0])} ${f(p2[1])}`;
  }
  return d + 'Z';
}

/// An open smooth curve through points.
export function curve(points, tension = 1) {
  const n = points.length;
  let d = `M${f(points[0][0])} ${f(points[0][1])}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = points[Math.max(0, i - 1)], p1 = points[i], p2 = points[i + 1], p3 = points[Math.min(n - 1, i + 2)];
    const c1 = [p1[0] + ((p2[0] - p0[0]) / 6) * tension, p1[1] + ((p2[1] - p0[1]) / 6) * tension];
    const c2 = [p2[0] - ((p3[0] - p1[0]) / 6) * tension, p2[1] - ((p3[1] - p1[1]) / 6) * tension];
    d += ` C${f(c1[0])} ${f(c1[1])} ${f(c2[0])} ${f(c2[1])} ${f(p2[0])} ${f(p2[1])}`;
  }
  return d;
}

/// A tapered stroke along a quadratic curve, as a filled shape: thick in the middle, pointed or
/// rounded at the ends. Good for brows, lid lines and feather bars.
export function taper(a, c, b, width, endWidth = 0) {
  const N = 14;
  const left = [], right = [];
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    const x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t ** 2 * b[0];
    const y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t ** 2 * b[1];
    const dx = 2 * (1 - t) * (c[0] - a[0]) + 2 * t * (b[0] - c[0]);
    const dy = 2 * (1 - t) * (c[1] - a[1]) + 2 * t * (b[1] - c[1]);
    const len = Math.hypot(dx, dy) || 1;
    const w = (endWidth + (width - endWidth) * Math.sin(Math.PI * t)) / 2;
    left.push([x - (dy / len) * w, y + (dx / len) * w]);
    right.push([x + (dy / len) * w, y - (dx / len) * w]);
  }
  const pts = left.concat(right.reverse());
  return 'M' + pts.map((p) => `${f(p[0])} ${f(p[1])}`).join(' L') + 'Z';
}

/// Merge a pose over defaults, filling per-side values from shared ones.
export function pose(defaults, p) {
  const o = { ...defaults, ...p };
  for (const k of Object.keys(o)) {
    if (k.endsWith('L') || k.endsWith('R')) continue;
    if (`${k}L` in defaults && o[`${k}L`] === null) o[`${k}L`] = o[k];
    if (`${k}R` in defaults && o[`${k}R`] === null) o[`${k}R`] = o[k];
  }
  return o;
}

let counter = 0;
export const uid = (prefix) => `${prefix}${++counter}`;

/// Wrap a figure's defs and body in an svg element at a given pixel size.
export function svg({ defs, body }, size, { viewBox = '0 0 200 200', title = '' } = {}) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="${size}" height="${size}" role="img" aria-label="${title}">${defs}${body}</svg>`;
}

/// Small marks around a figure, shared by all concepts so the comparison is about the figure.
export function extras(list, color, { x = 100, y = 60 } = {}) {
  const out = [];
  for (const e of list) {
    if (e === 'zzz') {
      out.push(`<g fill="${color}" font-family="ui-rounded, 'SF Pro Rounded', system-ui" font-weight="700" opacity="0.8">
        <text x="${x + 46}" y="${y + 6}" font-size="13">z</text><text x="${x + 56}" y="${y - 8}" font-size="10">z</text></g>`);
    }
    if (e === 'question') {
      out.push(`<text x="${x + 50}" y="${y + 4}" font-size="26" font-weight="800" fill="${color}" opacity="0.85" font-family="ui-rounded, 'SF Pro Rounded', system-ui">?</text>`);
    }
    if (e === 'spark') {
      for (const [sx, sy, s] of [[x + 54, y + 2, 1], [x - 52, y + 18, 0.6]]) {
        out.push(`<path transform="translate(${sx} ${sy}) scale(${s})" d="M0 -8 C1 -2 2 -1 8 0 C2 1 1 2 0 8 C-1 2 -2 1 -8 0 C-2 -1 -1 -2 0 -8Z" fill="${color}"/>`);
      }
    }
    if (e === 'think') {
      out.push(`<g fill="${color}" opacity="0.75"><circle cx="${x + 44}" cy="${y + 8}" r="2.6"/><circle cx="${x + 53}" cy="${y - 2}" r="3.4"/><circle cx="${x + 63}" cy="${y - 14}" r="4.4"/></g>`);
    }
  }
  return out.join('');
}

/// Milo's own cursor: a soft lavender arrow with a light edge.
export function cursor(x, y, scale = 1, color = '#7C6CD0') {
  return `<g transform="translate(${x} ${y}) scale(${scale})">
    <path d="M0 0 L0 22 L5.5 17 L9.5 26 L13 24.5 L9 16 L16 16 Z" fill="${color}" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></g>`;
}
