// Draws the favicon, app icons and the share card from the character rig, into public/.
//   bun run assets
// The share card is laid out in HTML and photographed with the local Chrome, so it uses the site's
// own fonts.
import sharp from 'sharp';
import { writeFileSync, readFileSync } from 'node:fs';
import { chromium } from 'playwright-core';
import { rig } from '../src/character/index.js';

const fig = (pose: string, uid: string, extra: Record<string, unknown> = {}, viewBox = '20 28 160 160') => {
  const { defs, body } = rig.draw({ ...rig.poses[pose], ...extra }, uid);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}">${defs}${body}</svg>`;
};

// Favicon: the whole bird, simplified, cropped tight so he reads at 16 px.
const icon = fig('idle', 'i', { small: true, pencil: 0, turn: -0.12 }, '30 36 146 146');
writeFileSync('public/icon.svg', icon);

const png = (svg: string, size: number) => sharp(Buffer.from(svg), { density: 600 }).resize(size, size).png().toBuffer();

// favicon.ico: one 32 px PNG inside an ICO wrapper.
const p32 = await png(icon, 32);
const head = Buffer.alloc(22);
head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(1, 4);
head.writeUInt8(32, 6); head.writeUInt8(32, 7); head.writeUInt8(0, 8); head.writeUInt8(0, 9);
head.writeUInt16LE(1, 10); head.writeUInt16LE(32, 12); head.writeUInt32LE(p32.length, 14); head.writeUInt32LE(22, 18);
writeFileSync('public/favicon.ico', Buffer.concat([head, p32]));

// App icons: Milo on his lavender paper, with room around him.
const tile = (size: number, pad = 0.14) => {
  const inner = fig('idle', `t${size}`, { turn: -0.15 }, '18 26 164 164');
  const s = Math.round(size * (1 - pad * 2));
  return png(inner, s).then((b) =>
    sharp({ create: { width: size, height: size, channels: 4, background: '#ece8fa' } })
      .composite([{ input: b, left: Math.round(size * pad), top: Math.round(size * pad * 1.15) }])
      .png().toBuffer());
};
writeFileSync('public/apple-touch-icon.png', await tile(180));
writeFileSync('public/icon-192.png', await tile(192));
writeFileSync('public/icon-512.png', await tile(512));

// Share card, 1200 x 630.
const font = (p: string) => readFileSync(`node_modules/@fontsource-variable/${p}`).toString('base64');
const milo = fig('happy', 'og', { turn: -0.25, lower: 0.6 }, '0 0 200 200');
const html = `<!doctype html><html><head><style>
@font-face { font-family: F; src: url(data:font/woff2;base64,${font('fraunces/files/fraunces-latin-soft-normal.woff2')}); font-weight: 100 900; }
@font-face { font-family: A; src: url(data:font/woff2;base64,${font('atkinson-hyperlegible-next/files/atkinson-hyperlegible-next-latin-wght-normal.woff2')}); font-weight: 200 800; }
html, body { margin: 0; }
body { width: 1200px; height: 630px; background: #f5f3fd; color: #2b2454; font-family: A; position: relative; overflow: hidden; }
.screen { position: absolute; right: -40px; bottom: -40px; width: 560px; height: 560px; border-radius: 48px; border: 16px solid #2b2454;
  background: radial-gradient(70% 60% at 80% 85%, #ffe7bd, transparent 70%), radial-gradient(90% 80% at 10% 0%, #d5ccf6, transparent 70%), linear-gradient(160deg, #e4defa, #efe6f4); }
.milo { position: absolute; right: 60px; bottom: 30px; width: 380px; height: 380px; }
.bubble { position: absolute; right: 330px; bottom: 380px; background: #fff; border-radius: 26px; padding: 18px 26px; font-size: 30px; box-shadow: 0 10px 30px -10px rgb(43 36 84 / .3); }
.bubble::after { content: ''; position: absolute; right: 40px; bottom: -9px; width: 22px; height: 22px; background: #fff; transform: rotate(45deg); border-radius: 0 0 5px 0; }
h1 { position: absolute; left: 80px; top: 150px; margin: 0; font-family: F; font-variation-settings: 'SOFT' 100; font-weight: 540; font-size: 132px; line-height: .95; letter-spacing: -0.035em; }
p { position: absolute; left: 84px; top: 455px; margin: 0; font-size: 34px; color: #59527f; }
.brand { position: absolute; left: 84px; top: 70px; font-family: F; font-variation-settings: 'SOFT' 100; font-weight: 620; font-size: 34px; letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }
.brand svg { width: 52px; height: 52px; }
</style></head><body>
<div class="brand">${fig('idle', 'b', { small: true, pencil: 0 }, '30 36 146 146')}Milo</div>
<h1>Just tell<br>Milo.</h1>
<p>Your coworker on the Mac.</p>
<div class="screen"></div>
<div class="bubble">On it.</div>
<div class="milo">${milo}</div>
</body></html>`;
const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
await page.setContent(html);
await page.evaluate(() => document.fonts.ready);
await page.screenshot({ path: 'public/og.png' });
await browser.close();

writeFileSync('public/manifest.webmanifest', JSON.stringify({
  name: 'Milo', short_name: 'Milo', start_url: '/', display: 'browser',
  background_color: '#f5f3fd', theme_color: '#6b5cbf',
  icons: [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png' }, { src: '/icon-512.png', sizes: '512x512', type: 'image/png' }],
}, null, 2));
console.log('icons and share card written to public/');
