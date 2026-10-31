// The Milo who lives on the page. He starts in the hero, flies into the bottom-right corner as you
// scroll (where he lives on a computer), watches from there, and flies out again to sit in the "Get
// Milo" section at the end. He follows your pointer with his eyes, falls asleep when you leave him
// alone, and waves when you come back.
import '../character/element.js';

type MiloEl = HTMLElement & {
  pose: string;
  extra: Record<string, number>;
  flying: boolean;
  blinking: boolean;
  life: boolean;
  play(name: string): Promise<void>;
  lookAt(x: number | null, y?: number): void;
};

const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(hover: hover) and (pointer: fine)');
const clamp = (v: number, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

const box = document.querySelector<HTMLElement>('[data-milo]')!;
const char = box.querySelector<MiloEl>('milo-character')!;
const bubble = box.querySelector<HTMLElement>('[data-milo-bubble]')!;
const hit = box.querySelector<HTMLButtonElement>('.milo-hit')!;
const heroSlot = document.querySelector<HTMLElement>('[data-milo-slot="hero"]')!;
const finalSlot = document.querySelector<HTMLElement>('[data-milo-slot="final"]');

/** Where Milo is: 'hero', 'flying', 'corner' or 'final'. */
let place = 'hero';
let sleeping = false;
let speaking = 0;

// ---------------------------------------------------------------- talking

let bubbleTimer = 0;
let mouthTimer = 0;
/** Show a line in his bubble, with his beak moving for a moment. */
export function say(text: string, ms = 3200) {
  clearTimeout(bubbleTimer);
  bubble.textContent = text;
  bubble.classList.add('is-on');
  talk(Math.min(1600, 260 + text.length * 38));
  if (ms > 0) bubbleTimer = window.setTimeout(hush, ms);
}
export function hush() {
  bubble.classList.remove('is-on');
}
/** Move his beak for a while, like he's saying something. */
export function talk(ms: number) {
  if (reduce.matches) return;
  const end = performance.now() + ms;
  speaking++;
  const id = speaking;
  clearTimeout(mouthTimer);
  const step = () => {
    if (id !== speaking) return;
    if (performance.now() > end) { char.extra = {}; return; }
    char.extra = { beak: 0.15 + Math.random() * 0.6 };
    mouthTimer = window.setTimeout(step, 85 + Math.random() * 60);
  };
  step();
}

export const milo = {
  el: char,
  box,
  say,
  hush,
  talk,
  get place() { return place; },
  get sleeping() { return sleeping; },
};

// ---------------------------------------------------------------- flying between hero, corner and end

let heroTop = 0, heroH = 0, finalTop = 0, finalH = 0, rem = 16;
const measure = () => {
  const y = scrollY;
  rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  const h = heroSlot.getBoundingClientRect();
  heroTop = h.top + y; heroH = h.height;
  if (finalSlot) {
    const f = finalSlot.getBoundingClientRect();
    finalTop = f.top + y; finalH = f.height;
  }
};

document.body.append(box);
box.classList.add('is-free');

let wasFlying = false;
let lastX = 0;
function place_() {
  const vw = document.documentElement.clientWidth, vh = innerHeight;
  const cs = vw < 720 ? 64 : rem * 6.6;
  const corner = { x: vw - cs - (vw < 720 ? 10 : 22), y: vh - cs - (vw < 720 ? 8 : 16), s: cs };

  const y = scrollY;
  const pHero = clamp((y - Math.max(0, heroTop + heroH * 0.5 - vh * 0.6)) / (vh * 0.45));
  const pFinal = finalSlot ? clamp((y - (finalTop + finalH * 0.5 - vh * 0.95)) / (vh * 0.32)) : 0;

  let from, to, t;
  const hr = heroSlot.getBoundingClientRect();
  if (pFinal > 0 && finalSlot) {
    const fr = finalSlot.getBoundingClientRect();
    from = corner; to = { x: fr.left, y: fr.top, s: fr.width }; t = pFinal;
  } else {
    from = { x: hr.left, y: hr.top, s: hr.width }; to = corner; t = pHero;
  }
  if (reduce.matches) t = t < 0.5 ? 0 : 1; // no flight, he is just there
  const e = ease(t);
  const arc = Math.sin(Math.PI * t) * Math.min(140, vh * 0.14);
  const x = lerp(from.x, to.x, e), yy = lerp(from.y, to.y, e) - arc, s = lerp(from.s, to.s, e);
  box.style.transform = `translate3d(${x.toFixed(1)}px, ${yy.toFixed(1)}px, 0)`;
  box.style.width = box.style.height = `${s.toFixed(1)}px`;
  box.classList.toggle('is-small', s < 150);

  const flying = t > 0.015 && t < 0.985;
  const prev = place;
  place = flying ? 'flying' : pFinal >= 0.985 ? 'final' : t >= 0.985 ? 'corner' : 'hero';
  if (flying) {
    if (!wasFlying) { hush(); wake(false); }
    const dx = x - lastX;
    char.flying = true;
    if (Math.abs(dx) > 0.5) char.extra = { turn: clamp(dx / 30, -0.5, 0.5) };
  } else if (wasFlying) {
    char.flying = false; // he lands with a squash and a bounce of the tail
    char.extra = {};
  }
  wasFlying = flying;
  lastX = x;
  duck();
  if (place !== prev) {
    if (prev === 'hero') hush();
    if (place === 'final') landedAtEnd();
    document.documentElement.dataset.milo = place;
    dispatchEvent(new CustomEvent('milo:place', { detail: place }));
  }
}

// Only one Milo on screen at a time: while a demo with its own Milo is in view, the corner one
// steps out of sight and comes back after.
const homes = new Set<Element>();
const duckIO = new IntersectionObserver((entries) => {
  for (const e of entries) e.isIntersecting ? homes.add(e.target) : homes.delete(e.target);
  duck();
}, { threshold: 0.3 });
document.querySelectorAll('[data-has-milo]').forEach((el) => duckIO.observe(el));
function duck() {
  const on = place === 'corner' && homes.size > 0;
  if (on && !box.classList.contains('is-ducked')) hush();
  box.classList.toggle('is-ducked', on);
}

let landedOnce = false;
function landedAtEnd() {
  if (landedOnce) return;
  landedOnce = true;
  setTimeout(() => {
    char.pose = 'happy';
    say("I'll be here.", 2600);
    setTimeout(() => { if (char.pose === 'happy') char.pose = 'idle'; }, 1800);
  }, 250);
}

let frame = 0;
const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; place_(); }); };
addEventListener('scroll', schedule, { passive: true });

// On a phone the corner is part of what you read, so he steps out of the way while you scroll and
// comes back when you stop.
const narrow = matchMedia('(max-width: 44.99rem)');
let scrollIdle = 0;
addEventListener('scroll', () => {
  if (!narrow.matches || place !== 'corner') return;
  box.classList.add('is-aside');
  clearTimeout(scrollIdle);
  scrollIdle = window.setTimeout(() => box.classList.remove('is-aside'), 1100);
}, { passive: true });
addEventListener('resize', () => { measure(); schedule(); });
new ResizeObserver(() => { measure(); schedule(); }).observe(document.body);
measure();
place_();

// ---------------------------------------------------------------- eyes on your pointer

let lastPointer = 0;
let lookFrame = 0;
let px = 0, py = 0;
let watching: HTMLElement | null = null;
addEventListener('pointermove', (e) => {
  if (e.pointerType !== 'mouse') return;
  px = e.clientX; py = e.clientY;
  lastPointer = performance.now();
  if (!lookFrame) lookFrame = requestAnimationFrame(() => {
    lookFrame = 0;
    if (!sleeping) char.lookAt(px, py);
  });
}, { passive: true });
// He loses interest a few seconds after the pointer stops, and goes back to what he was watching.
setInterval(() => {
  if (sleeping || !lastPointer) return;
  if (performance.now() - lastPointer > 3500) {
    lastPointer = 0;
    lookAtWatched();
  }
}, 1000);

function lookAtWatched() {
  if (watching && place === 'corner') {
    const r = watching.getBoundingClientRect();
    if (r.bottom > 0 && r.top < innerHeight) return char.lookAt(r.left + r.width / 2, r.top + r.height / 2);
  }
  char.lookAt(null);
}

/** Demos call this so the corner Milo keeps an eye on what's happening. */
export function watch(el: HTMLElement | null) {
  watching = el;
  if (!lastPointer) lookAtWatched();
}

// ---------------------------------------------------------------- hello, sleep and waking up

const hello = {
  hero: ['Hello.', "I'm Milo. I live down in the corner.", "Scroll down, I'll show you."],
  corner: ['Still here.', "I'm watching. Quietly.", 'Press esc and I stop. Try it in the spreadsheet.', 'This page has no cookies. I checked.'],
  final: ["I'll be here.", 'Room for one more.', 'See you on your computer.'],
} as Record<string, string[]>;
const helloCount: Record<string, number> = {};
hit.addEventListener('click', () => {
  if (sleeping) return wake(true);
  const list = hello[place] ?? hello.corner;
  const i = (helloCount[place] = ((helloCount[place] ?? -1) + 1) % list.length);
  char.play('hop');
  say(list[i]);
});
let lastHop = 0;
hit.addEventListener('pointerenter', (e) => {
  if (e.pointerType !== 'mouse') return;
  if (sleeping) return wake(true);
  if (performance.now() - lastHop > 5000) { lastHop = performance.now(); char.play('hop'); }
});

const IDLE_MS = 45_000;
let idleTimer = 0;
function resetIdle() {
  clearTimeout(idleTimer);
  if (sleeping) wake(true);
  idleTimer = window.setTimeout(fallAsleep, IDLE_MS);
}
async function fallAsleep() {
  if (sleeping || place === 'flying' || document.visibilityState !== 'visible') return;
  sleeping = true;
  hush();
  char.lookAt(null);
  await char.play('yawn');
  if (!sleeping) return;
  char.pose = 'sleepy';
  char.blinking = false;
  box.dataset.state = 'sleeping';
}
async function wake(waveHello: boolean) {
  if (!sleeping) return;
  sleeping = false;
  delete box.dataset.state;
  char.blinking = true;
  char.pose = 'idle';
  if (waveHello && !reduce.matches) {
    await new Promise((r) => setTimeout(r, 260));
    char.play('wave');
  }
}
for (const ev of ['pointermove', 'pointerdown', 'keydown', 'scroll', 'touchstart']) {
  addEventListener(ev, resetIdle, { passive: true });
}
resetIdle();

// Away from the tab for a while: a wave when you come back.
let hiddenAt = 0;
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') { hiddenAt = performance.now(); return; }
  if (hiddenAt && performance.now() - hiddenAt > 8000) {
    if (sleeping) wake(true);
    else if (place !== 'flying' && !reduce.matches) setTimeout(() => char.play('wave'), 300);
  }
  resetIdle();
});

// Esc anywhere: he stops what he's doing (the demos listen too).
addEventListener('keydown', (e) => {
  if (e.key === 'Escape') hush();
});

if (!finePointer.matches) char.lookAt(null);
// now and then, while nothing happens, a glance, a bob, a tail flick or a tug at his scarf
char.life = true;
