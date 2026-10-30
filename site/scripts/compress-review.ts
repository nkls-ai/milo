// Turns the PNG screenshots in review/<pass> into WebP so the review folder stays small enough for git.
//   bun scripts/compress-review.ts review/p1-before
import sharp from 'sharp';
import { readdirSync, statSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';

const walk = (d: string): string[] => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]));
for (const dir of process.argv.slice(2)) {
  for (const f of walk(dir).filter((f) => f.endsWith('.png'))) {
    const img = sharp(f);
    const { width = 0 } = await img.metadata();
    // full-page overviews and 2x shots wider than 1600 px are halved; text stays readable
    await img.resize({ width: Math.min(width, 1600) }).webp({ quality: 80 }).toFile(f.replace(/\.png$/, '.webp'));
    unlinkSync(f);
  }
}
