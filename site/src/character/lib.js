// Small helpers for the rig: a defs registry, pose merging, a point rotation and the marks drawn
// around him (zzz, ?, sparkle, thought dots).

export function rotPt([x, y], deg, [cx, cy]) {
  const a = (deg * Math.PI) / 180;
  const dx = x - cx, dy = y - cy;
  return [cx + dx * Math.cos(a) - dy * Math.sin(a), cy + dx * Math.sin(a) + dy * Math.cos(a)];
}

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

/// Small marks around him: zzz and thought dots in lavender, the question mark and sparkle in marigold.
export function extras(list, color, { x = 100, y = 60, warm = color } = {}) {
  const out = [];
  for (const e of list) {
    if (e === 'zzz') {
      out.push(`<g fill="${color}" font-family="ui-rounded, 'SF Pro Rounded', system-ui" font-weight="700" opacity="0.8">
        <text x="${x + 46}" y="${y + 6}" font-size="13">z</text><text x="${x + 56}" y="${y - 8}" font-size="10">z</text></g>`);
    }
    if (e === 'question') {
      out.push(`<text x="${x + 50}" y="${y + 4}" font-size="26" font-weight="800" fill="${warm}" opacity="0.85" font-family="ui-rounded, 'SF Pro Rounded', system-ui">?</text>`);
    }
    if (e === 'spark') {
      for (const [sx, sy, s] of [[x + 54, y + 2, 1], [x - 52, y + 18, 0.6]]) {
        out.push(`<path transform="translate(${sx} ${sy}) scale(${s})" d="M0 -8 C1 -2 2 -1 8 0 C2 1 1 2 0 8 C-1 2 -2 1 -8 0 C-2 -1 -1 -2 0 -8Z" fill="${warm}"/>`);
      }
    }
    if (e === 'think') {
      out.push(`<g fill="${color}" opacity="0.75"><circle cx="${x + 44}" cy="${y + 8}" r="2.6"/><circle cx="${x + 53}" cy="${y - 2}" r="3.4"/><circle cx="${x + 63}" cy="${y - 14}" r="4.4"/></g>`);
    }
  }
  return out.join('');
}
