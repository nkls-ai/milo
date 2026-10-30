// Puts screenshots side by side for review: bun scripts/montage.ts out.png a.png b.png ... [--h=2000]
import sharp from 'sharp';
const args = process.argv.slice(2);
const h = Number(args.find((a) => a.startsWith('--h='))?.slice(4) ?? 2000);
const [out, ...files] = args.filter((a) => !a.startsWith('--'));
const imgs = await Promise.all(files.map(async (f) => {
  const b = await sharp(f).resize({ height: h, fit: 'inside', withoutEnlargement: true }).toBuffer();
  return { b, w: (await sharp(b).metadata()).width! };
}));
let x = 0;
const comp = imgs.map((i) => { const c = { input: i.b, left: x, top: 0 }; x += i.w + 12; return c; });
await sharp({ create: { width: x, height: h, channels: 3, background: '#888' } }).composite(comp).png().toFile(out);
