// Builds nothing: serves dist/ locally, runs Lighthouse (mobile and desktop) with the local Chrome,
// prints the four scores and saves the reports in review/lighthouse/.   bun run lighthouse
import { mkdirSync } from 'node:fs';
import { $ } from 'bun';

const port = 4392;
const server = Bun.spawn(['bun', 'scripts/serve.ts', String(port)], { stdout: 'ignore', stderr: 'inherit' });
await Bun.sleep(600);
mkdirSync('review/lighthouse', { recursive: true });
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const results: Record<string, Record<string, number>> = {};
try {
  for (const form of ['mobile', 'desktop']) {
    const out = `review/lighthouse/${form}`;
    const preset = form === 'desktop' ? ['--preset=desktop'] : [];
    await $`bunx lighthouse http://localhost:${port}/ --quiet --chrome-path=${chrome} --chrome-flags=--headless=new ${preset} --output=json --output=html --output-path=${out}`.quiet();
    const report = await Bun.file(`${out}.report.json`).json();
    results[form] = Object.fromEntries(Object.entries(report.categories).map(([k, v]: [string, any]) => [k, Math.round(v.score * 100)]));
    const a = report.audits;
    results[form].LCP_ms = Math.round(a['largest-contentful-paint'].numericValue);
    results[form].CLS = Number(a['cumulative-layout-shift'].numericValue.toFixed(3));
    results[form].TBT_ms = Math.round(a['total-blocking-time'].numericValue);
  }
} finally {
  server.kill();
}
console.table(results);
