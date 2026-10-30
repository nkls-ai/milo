// Screenshots every section at 390, 1440 and 2560 px, light and dark, into review/<pass>/.
//   bun scripts/shoot.ts <pass> [url] [--only=hero,talk] [--widths=390,1440] [--motion]
// Without --motion the page runs with reduced motion, so demos show their finished state.
import { chromium } from 'playwright-core';
import { mkdirSync } from 'node:fs';
import sharp from 'sharp';

const args = process.argv.slice(2);
const pass = args.find((a) => !a.startsWith('-') ) ?? 'scratch';
const url = args.filter((a) => !a.startsWith('-'))[1] ?? 'http://localhost:4321/';
const only = args.find((a) => a.startsWith('--only='))?.slice(7).split(',');
const widths = args.find((a) => a.startsWith('--widths='))?.slice(9).split(',').map(Number) ?? [390, 1440, 2560];
const themes = (args.find((a) => a.startsWith('--themes='))?.slice(9).split(',') ?? ['light', 'dark']) as ('light' | 'dark')[];
const motion = args.includes('--motion');
const out = `review/${pass}`;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome' });
for (const width of widths) {
  for (const theme of themes) {
    const page = await browser.newPage({
      viewport: { width, height: width < 600 ? 844 : width > 2000 ? 1440 : 900 },
      deviceScaleFactor: width > 2000 ? 1 : 2,
      colorScheme: theme,
      reducedMotion: motion ? 'no-preference' : 'reduce',
    });
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log(`[${width} ${theme}] console ${m.type()}: ${m.text()}`); });
    page.on('pageerror', (e) => console.log(`[${width} ${theme}] page error: ${e.message}`));
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    const ids: string[] = await page.$$eval('header.nav, main > section, footer', (els) => els.map((e, i) => e.id || (e.tagName === 'HEADER' ? 'nav' : e.tagName === 'FOOTER' ? 'footer' : `s${i}`)));
    const shots: string[] = [];
    for (const id of ids) {
      if (only && !only.includes(id)) continue;
      const sel = id === 'nav' ? 'header.nav' : id === 'footer' ? 'footer' : `#${id}`;
      const el = page.locator(sel).first();
      // the sticky nav would otherwise be printed over the top of every section
      await page.evaluate((isNav) => { document.querySelector<HTMLElement>('header.nav')!.style.visibility = isNav ? '' : 'hidden'; }, id === 'nav');
      await el.scrollIntoViewIfNeeded();
      await page.waitForTimeout(motion ? 2500 : 500);
      const file = `${out}/${id}-${width}-${theme}.png`;
      await el.screenshot({ path: file, animations: motion ? 'allow' : 'disabled' });
      shots.push(file);
    }
    if (!only) {
      await page.evaluate(() => { document.querySelector<HTMLElement>('header.nav')!.style.visibility = ''; scrollTo(0, 0); });
      await page.waitForTimeout(600);
      // Chrome can't capture more than 16k px in one go, so the overview is taken at 1x.
      const full = await browser.newPage({ viewport: page.viewportSize()!, deviceScaleFactor: 1, colorScheme: theme, reducedMotion: 'reduce' });
      await full.goto(url, { waitUntil: 'networkidle' });
      await full.evaluate(() => document.fonts.ready);
      await full.waitForTimeout(400);
      await full.screenshot({ path: `${out}/_full-${width}-${theme}.png`, fullPage: true });
      await full.close();
    }
    await page.close();
    console.log(width, theme, shots.length);
  }
}
await browser.close();
