// Serves dist/ with gzip and long caching for hashed files, the way a static host would.
//   bun scripts/serve.ts [port=4392]
import { file } from 'bun';
import { join, normalize } from 'node:path';

const port = Number(process.argv[2] ?? 4392);
const root = join(import.meta.dir, '..', 'dist');
const zippable = /\.(html|js|css|svg|json|webmanifest|txt)$/;

const server = Bun.serve({
  port,
  async fetch(req) {
    let path = normalize(decodeURIComponent(new URL(req.url).pathname));
    if (path.endsWith('/')) path += 'index.html';
    const f = file(join(root, path));
    if (!path.startsWith('/') || !(await f.exists())) return new Response('Not found', { status: 404 });
    const headers: Record<string, string> = {
      'content-type': f.type,
      'cache-control': path.startsWith('/_astro/') ? 'public, max-age=31536000, immutable' : 'public, max-age=600',
      'x-content-type-options': 'nosniff',
    };
    if (zippable.test(path) && (req.headers.get('accept-encoding') ?? '').includes('gzip')) {
      headers['content-encoding'] = 'gzip';
      headers.vary = 'accept-encoding';
      return new Response(Bun.gzipSync(new Uint8Array(await f.arrayBuffer())), { headers });
    }
    return new Response(f, { headers });
  },
});
console.log(`serving dist/ on http://localhost:${server.port}`);
