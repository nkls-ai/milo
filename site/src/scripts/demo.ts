// A small runner for the demos. A demo plays once when you scroll to it, can be played again, and
// stops cleanly when restarted. With reduced motion it doesn't animate: it jumps straight to its
// finished state, and "Play again" does the same.
import { watch } from './milo';
import '../character/element.js';

export const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

export class Stopped extends Error {}

export interface Ctx {
  /** Wait, or throw Stopped if the demo was restarted or stopped. Instant with reduced motion. */
  wait(ms: number): Promise<void>;
  /** True while this run is still the current one. */
  readonly live: boolean;
  readonly instant: boolean;
  /** Type text into an element character by character. */
  type(el: HTMLElement, text: string, cps?: number): Promise<void>;
}

export interface Demo {
  play(): void;
  stop(): void;
  readonly running: boolean;
}

export function demo(
  root: HTMLElement,
  run: (ctx: Ctx) => Promise<void>,
  { reset, autoplay = true, threshold = 0.45 }: { reset?: () => void; autoplay?: boolean; threshold?: number } = {},
): Demo {
  let token = 0;
  let running = false;
  const play = async () => {
    const me = ++token;
    reset?.();
    running = true;
    root.dataset.running = '';
    if (!reduce) watch(root);
    const ctx: Ctx = {
      instant: reduce,
      get live() { return me === token; },
      wait: (ms) => new Promise((ok, no) => {
        if (me !== token) return no(new Stopped());
        if (reduce) return ok();
        setTimeout(() => (me === token ? ok() : no(new Stopped())), ms);
      }),
      async type(el, text, cps = 28) {
        if (reduce) { el.textContent = text; return; }
        for (let i = 1; i <= text.length; i++) {
          el.textContent = text.slice(0, i);
          await ctx.wait(1000 / cps * (text[i - 1] === ' ' ? 0.6 : 1) * (0.7 + Math.random() * 0.6));
        }
      },
    };
    try {
      await run(ctx);
    } catch (e) {
      if (!(e instanceof Stopped)) throw e;
    } finally {
      if (me === token) {
        running = false;
        delete root.dataset.running;
        watch(null);
      }
    }
  };
  const d: Demo = {
    play,
    stop() { token++; running = false; delete root.dataset.running; watch(null); },
    get running() { return running; },
  };
  root.querySelector('[data-replay]')?.addEventListener('click', () => play());
  if (reduce) play();
  else if (autoplay) {
    const io = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { io.disconnect(); play(); }
    }, { threshold });
    io.observe(root);
  }
  return d;
}

export type MiloEl = HTMLElement & {
  pose: string;
  extra: Record<string, number>;
  flying: boolean;
  play(name: string): Promise<void>;
  lookAt(x: number | null, y?: number): void;
};

/** Move a Milo's beak for a while. */
export function chatter(el: MiloEl, ms: number) {
  if (reduce) return;
  const end = performance.now() + ms;
  const step = () => {
    if (performance.now() > end) { el.extra = {}; return; }
    el.extra = { beak: 0.15 + Math.random() * 0.6 };
    setTimeout(step, 85 + Math.random() * 60);
  };
  step();
}

export const $ = <T extends HTMLElement = HTMLElement>(root: ParentNode, sel: string) => root.querySelector<T>(sel)!;
export const $$ = <T extends HTMLElement = HTMLElement>(root: ParentNode, sel: string) => [...root.querySelectorAll<T>(sel)];
