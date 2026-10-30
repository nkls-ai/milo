// Builds one expression sheet per concept as HTML and renders it to PNG with headless Chrome.
//   node sheet.mjs wren v1        -> ../wren-v1.png
//   node sheet.mjs all v1
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { svg, uid } from './lib.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, '..');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

export const LIGHT = '#F3F1F8';
export const DARK = '#1C1A28';

export async function load(name) {
  return import(`./${name}.mjs?${Date.now()}`);
}

export function fig(c, p, size, opts = {}) {
  return svg(c.draw(p, uid(c.name.toLowerCase().slice(0, 2))), size, opts);
}

/// The figure as one flat dark shape, to judge the silhouette.
export function silhouette(c, p, size, color = '#26222F') {
  const id = uid('sil');
  const { defs, body } = c.draw({ ...p, extras: [], cursorAt: null }, id);
  const filt = `<filter id="${id}-f"><feFlood flood-color="${color}"/><feComposite in2="SourceAlpha" operator="in"/></filter>`;
  return `<svg viewBox="0 0 200 200" width="${size}" height="${size}">${defs.replace('</defs>', filt + '</defs>')}<g filter="url(#${id}-f)">${body}</g></svg>`;
}

export function sheetHTML(c, version, note = '') {
  const states = c.states;
  const cell = (label, inner, bg = LIGHT, fg = '#3A3550') =>
    `<div class="cell" style="background:${bg};color:${fg}">${inner}<div class="lab">${label}</div></div>`;
  const hero = [
    cell('front', fig(c, { turn: 0 }, 300)),
    cell('three-quarter', fig(c, {}, 300)),
    cell('other side', fig(c, { turn: -0.5, gx: -0.4 }, 300)),
    cell('silhouette', silhouette(c, {}, 300)),
  ].join('');
  const grid = states.map(([n, p]) => cell(n, fig(c, p, 132))).join('');
  const darkGrid = states.slice(0, 6).map(([n, p]) => cell(n, fig(c, p, 132), DARK, '#CFCAE6')).join('');
  const smallStates = ['idle', 'working', 'flying', 'happy', 'sleepy', 'confused'];
  const small = (bg) =>
    smallStates
      .map((n) => fig(c, { ...Object.fromEntries(states)[n], small: true, extras: [], cursorAt: null }, 36))
      .join('');
  const ladder = `
    <div class="ladder" style="background:${LIGHT}">${fig(c, {}, 300)}${fig(c, {}, 132)}${fig(c, { small: true }, 36)}<div class="smalls">${small(LIGHT)}</div><div class="smalls">${smallStates.map((n) => silhouette(c, { ...Object.fromEntries(states)[n], small: true }, 36)).join('')}</div></div>
    <div class="ladder" style="background:${DARK}">${fig(c, {}, 300)}${fig(c, {}, 132)}${fig(c, { small: true }, 36)}<div class="smalls">${small(DARK)}</div></div>`;
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;background:#E9E6F0;font:13px -apple-system,system-ui;color:#2B2740;width:1200px}
  h1{font:600 22px -apple-system,system-ui;margin:18px 22px 4px} .note{margin:0 22px 12px;color:#5B5570}
  .row{display:flex;flex-wrap:wrap;gap:8px;padding:0 22px 8px}
  .cell{border-radius:14px;display:flex;flex-direction:column;align-items:center;padding:6px 6px 8px}
  .lab{font-size:12px;margin-top:2px;opacity:.8}
  .ladder{display:flex;align-items:flex-end;gap:18px;padding:12px 18px;border-radius:14px;margin:0 22px 8px}
  .smalls{display:flex;gap:8px;align-items:flex-end;padding-bottom:6px}
  </style></head><body>
  <h1>Milo · ${c.name} · ${version}</h1><div class="note">${note}</div>
  <div class="row">${hero}</div>
  <div class="row">${grid}</div>
  <div class="row">${darkGrid}</div>
  ${ladder}
  </body></html>`;
}

export function render(html, png, width = 1200, height = 1500) {
  const tmp = `/tmp/milo12/${Date.now()}-${Math.random().toString(36).slice(2)}.html`;
  mkdirSync('/tmp/milo12', { recursive: true });
  writeFileSync(tmp, html);
  execFileSync(CHROME, [
    '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
    '--user-data-dir=/tmp/milo12/chrome', `--window-size=${width},${height}`, '--force-device-scale-factor=1',
    `--screenshot=${png}`, `file://${tmp}`,
  ], { stdio: 'ignore' });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [which = 'all', version = 'v1'] = process.argv.slice(2);
  const names = which === 'all' ? ['wren', 'moth', 'sprite'] : [which];
  for (const n of names) {
    const c = await load(n);
    const png = join(outDir, `${n}-${version}.png`);
    render(sheetHTML(c, version, c.note ?? ''), png, 1200, 1520);
    console.log(png);
  }
}
