// Cuts a tall screenshot into viewable pieces: bun scripts/slice.ts <png> [width=1000] [pieceHeight=1800]
import sharp from 'sharp';
const [file, w = '1000', ph = '1800'] = process.argv.slice(2);
const img = sharp(file).resize({ width: Number(w) });
const buf = await img.png().toBuffer();
const { height } = await sharp(buf).metadata();
const n = Math.ceil(height! / Number(ph));
for (let i = 0; i < n; i++) {
  const top = i * Number(ph);
  await sharp(buf).extract({ left: 0, top, width: Number(w), height: Math.min(Number(ph), height! - top) }).toFile(file.replace('.png', `.part${i}.png`).replace('review/', '/tmp/milo-slices/'));
}
console.log(n, 'pieces');
