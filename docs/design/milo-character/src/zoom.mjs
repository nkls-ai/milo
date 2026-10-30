// node zoom.mjs wren '{"turn":0.18}' out.png [size]  -> one figure, large, light and dark side by side
import { fig, load, render, LIGHT, DARK } from './sheet.mjs';
const [n, json = '{}', out = '/tmp/milo12/zoom.png', size = '520'] = process.argv.slice(2);
const c = await load(n);
const poses = JSON.parse(json);
const list = Array.isArray(poses) ? poses : [poses];
const s = Number(size);
const html = `<body style="margin:0;display:flex;flex-wrap:wrap;width:${s * Math.min(list.length, 3) * 1 + 0}px">${list
  .map((p, i) => `<div style="background:${i % 2 && list.length > 1 && p._dark ? DARK : (p._dark ? DARK : LIGHT)}">${fig(c, p, s)}</div>`)
  .join('')}</body>`;
render(html, out, s * Math.min(list.length, 3), s * Math.ceil(list.length / 3));
console.log(out);
