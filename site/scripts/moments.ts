// Screenshots of things that only exist in motion: Milo flying, in the corner, asleep, waving,
// demos halfway through, focus rings. bun scripts/moments.ts <pass> [url]
import { chromium, type Page } from 'playwright-core';
import { mkdirSync } from 'node:fs';

const pass = process.argv[2] ?? 'scratch';
const url = process.argv[3] ?? 'http://localhost:4321/';
const out = `review/${pass}/moments`;
mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome' });

async function open(width: number, theme: 'light' | 'dark' = 'light') {
  const page = await browser.newPage({ viewport: { width, height: width < 600 ? 844 : 900 }, deviceScaleFactor: 2, colorScheme: theme });
  page.on('pageerror', (e) => console.log('page error:', e.message));
  page.on('console', (m) => { if (m.type() === 'error') console.log('console:', m.text()); });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  return page;
}
const shot = (page: Page, name: string) => page.screenshot({ path: `${out}/${name}.png` });
const scrollTo = async (page: Page, sel: string, block = 'center') => {
  await page.evaluate(([s, b]) => document.querySelector(s)!.scrollIntoView({ block: b as ScrollLogicalPosition, behavior: 'instant' }), [sel, block]);
};

for (const [w, theme] of [[1440, 'light'], [390, 'light'], [1440, 'dark']] as const) {
  const tag = `${w}-${theme}`;
  const page = await open(w, theme);
  await page.mouse.move(w * 0.3, 300);
  await page.waitForTimeout(3200);
  await shot(page, `hero-talking-${tag}`);
  // mid-flight
  await page.evaluate(() => scrollTo({ top: innerHeight * 0.22, behavior: 'instant' }));
  await page.waitForTimeout(250);
  await shot(page, `flying-${tag}`);
  // in the corner, next to a section without its own Milo
  await scrollTo(page, '#trust', 'start');
  await page.waitForTimeout(1200);
  await shot(page, `corner-${tag}`);
  // the prices
  await scrollTo(page, '#pricing [data-plans]');
  await page.waitForTimeout(1500);
  await shot(page, `pricing-remark-${tag}`);
  // demos halfway
  for (const [id, ms] of [['work', 3800], ['helpers', 3000], ['meetings', 5500], ['phone', 4200], ['dictation', 2600], ['talk', 0]] as const) {
    await scrollTo(page, `#${id} .feature > :last-child`);
    await page.waitForTimeout(ms);
    if (id === 'talk') {
      const hold = page.locator('[data-hold]');
      await hold.hover();
      await page.mouse.down();
      await page.waitForTimeout(1300);
      await shot(page, `talk-holding-${tag}`);
      await page.mouse.up();
      await page.waitForTimeout(2600);
    }
    await shot(page, `${id}-mid-${tag}`);
  }
  // the end
  await scrollTo(page, '#waitlist', 'center');
  await page.waitForTimeout(1600);
  await shot(page, `final-${tag}`);
  await page.close();
}

// asleep, then waving when you come back
{
  const page = await open(1440);
  await scrollTo(page, '#trust', 'start');
  await page.waitForTimeout(47000);
  await shot(page, 'asleep-1440-light');
  await page.mouse.move(700, 400);
  await page.mouse.move(720, 420);
  await page.waitForTimeout(700);
  await shot(page, 'waving-1440-light');
  // keyboard focus
  await page.evaluate(() => scrollTo(0, 0));
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(200);
  await shot(page, 'focus-nav-1440-light');
  await scrollTo(page, '#faq');
  await page.locator('#faq summary').first().focus();
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  await shot(page, 'focus-faq-1440-light');
  await page.close();
}
await browser.close();
