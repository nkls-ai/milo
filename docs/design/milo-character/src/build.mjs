// Builds docs/design/milo-character.html (all figures inline SVG) and the overview PNGs next to it.
//   node build.mjs
import { existsSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { svg, uid } from './lib.mjs';
import { DARK, LIGHT, TIGHT, load, render, silhouette } from './sheet.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const pngDir = join(here, '..');
const page = join(here, '..', '..', 'milo-character.html');

const wren = await load('wren'), moth = await load('moth'), sprite = await load('sprite');
const S = (c) => Object.fromEntries(c.states);
const fig = (c, p, size, viewBox) => svg(c.draw(p, uid(c.name[0].toLowerCase())), size, viewBox ? { viewBox } : {});

/// One gesture per concept, as key poses, to show it animates as blends of the same parameters.
const strips = {
  Wren: {
    title: 'Starts a task: looks down, tosses the scarf over his shoulder, gets to it',
    frames: [
      [{}, 'idle'],
      [{ gy: 0.9, gx: 0.3, headTilt: -6, squash: -0.035, lid: 0.35 }, 'anticipation: looks down, squashes'],
      [{ scarfToss: 0.42, squash: 0.04, lift: 3, wingR: 40, wingOpenR: 0, lid: 0.2, brow: 0.3 }, 'the toss: stretches, wing flicks'],
      [{ scarfToss: 1, turn: -0.35, squash: -0.02, lid: 0.3, gx: -0.6 }, 'settles, scarf lands behind'],
      [S(wren).working, 'working, cursor out'],
    ],
  },
  Moth: {
    title: 'Turns in for the night: a yawn, then he wraps himself in his wings',
    frames: [
      [{}, 'idle'],
      [{ mouth: 0.9, lid: 0.7, brow: -0.6, headTilt: -4, squash: 0.03 }, 'yawn, antennae sag'],
      [{ wrap: 0.5, lid: 0.85, brow: -0.8, squash: -0.02 }, 'wings start to close'],
      [{ wrap: 1, lid: 1, brow: -1, squash: -0.05, headTilt: -8 }, 'wrapped'],
      [S(moth).sleepy, 'asleep'],
    ],
  },
  Sprite: {
    title: "Doesn't get it: the hood tip slowly curls into a question",
    frames: [
      [{}, 'idle'],
      [{ headTilt: 5, tip: 0.3, tipCurl: 0.4, browR: 0.4 }, 'head tilts'],
      [{ headTilt: 9, tip: 0.4, tipCurl: 1, browR: 0.8, browL: -0.3 }, 'tip starts to curl'],
      [{ headTilt: 11, tip: 0.4, tipCurl: 1.6, browR: 1, browL: -0.6, eyeScaleL: 0.8 }, 'the curl lands'],
      [S(sprite).confused, 'says what he missed'],
    ],
  },
};

const concepts = [
  {
    c: wren, key: 'wren', versions: ['v1', 'v2', 'v3', 'v4'],
    pitch: 'A round lavender wren. Wrens are small, loud for their size, and nest in the corners of houses, which is where Milo lives. He keeps the bird we already have (helpers are small birds, he flies to the window he works in) and adds three things nobody else has: a tail cocked up behind his back that works as a mood meter, pale brow stripes that real wrens have and that give him a dry, readable face, and a marigold knitted scarf with one loose end and a pencil tucked in it.',
    signatures: ['Cocked tail, peeking up behind the shoulder away from you. Up and fanned when pleased, low when worried, ticking while he waits for a yes.', 'Pale brow stripes. Real wren markings, so the brows are part of the bird, not stuck on. One lifted brow is his whole sense of humour.', 'Marigold scarf with a pencil in it. He tosses the loose end over his shoulder to start a job and pulls it over his beak to sleep.'],
    critique: [
      ['v1', 'Eyes too small under heavy lids: he read as grumpy, not dry. A hard rim-light outline. The far wing poked out like a backpack. A spiky dark tail fan read as a hand. Belly marks looked like rows of little smiles.'],
      ['v2', 'Bigger, calmer eyes and a soft rim light. One feather-fan tail. But flat-coloured lids showed as pale discs on the gradient body, and the tail read as a raised club.'],
      ['v3', 'Lids now use the body gradient, so they disappear until they move. He faces the screen centre by default. The pointing wing became an open fan whose primaries read as fingers. Flight still looked like a ball with paddles.'],
      ['v4', 'Smiling eyes are clean arches. Wings rise in a V to fly while the scarf streams behind (follow-through you get for free). Concerned brows tilted the wrong way, which read as angry, so I flipped them. Added the pencil.'],
    ],
    scores: { before: [3, 3, 3, 2.5, 4, 4, 3], after: [4.5, 3.5, 4, 4.5, 5, 5, 4] },
    risks: 'A round bird in a scarf is close to a Christmas-card robin. The lavender, the brow stripes, the cocked tail and the gestures keep him apart, but the body shape alone is not ownable. The pencil is lost below about 80 pt; the scarf carries him at helper size.',
  },
  {
    c: moth, key: 'moth', versions: ['v2', 'v3'],
    pitch: 'A fluffy lavender moth who lives by the light of your screen. Moths come to a lit window at night, and he came to yours. Feathery antennae are his eyebrows, a cream ruff is his collar, and his folded wings hang like a cardigan with two marigold "lamp" spots. To sleep he wraps himself up in them.',
    signatures: ['Feathery antennae that act as brows: perk up to listen, droop when worried, one up and one bent when confused.', 'Wings worn like a cardigan, with two marigold lamp spots. Open, they make the boldest silhouette of the three.', 'Wraps himself in his wings to sleep, like a cocoon.'],
    critique: [
      ['v1', 'The wings were mirrored the wrong way and hid behind the body, so he read as a doll in a skirt. Thin arms looped like a purse strap. Small lidded eyes looked bored.'],
      ['v2', 'The wings now hang outward like a cardigan and the lamp spots show. But spread wide they read as a butterfly, and the big glossy eyes leaned anime.'],
      ['v3', 'Wings tucked halfway in. Eyes a little smaller, set wider and lower so there is more face. Antennae moved right over the eyes so they read as brows. Fur strands on the crown.'],
    ],
    scores: { before: [3, 4.5, 3, 2.5, 3, 3.5, 4], after: [4, 5, 4, 3.5, 3, 4, 4.5] },
    risks: 'Some people dislike insects, and the user\'s mom is the audience. His wings are wider than the 120 pt box the corner gives him, so they clip at 132 pt. "Helpers" would be small moths, which some people would not want flying around their screen.',
  },
  {
    c: sprite, key: 'sprite', versions: ['v2', 'v3'],
    pitch: 'A house sprite: the small helper from folklore who tidies while the family is out. He wears a knitted lavender hood that becomes a capelet, with a long floppy tip ending in a marigold tassel. The face inside is a creature\'s, not a person\'s: pale, with a plum nose.',
    signatures: ['The hood tip is his tail: it stands up to listen, droops when worried, and curls into a question mark when confused.', 'Knitted texture and a marigold hem stripe. He is made of something warm.', 'Pulls the hood down over his eyes to sleep.'],
    critique: [
      ['v1', 'He read as a human child in a cloak, with a beige skin face. That breaks "he doesn\'t pretend to be a person". The bell was too tall and the pointing arm was a stick.'],
      ['v2', 'Creature face and plum nose, a shorter capelet, mitten arms. But the dark rim made the face look like a space helmet, the idle mittens looked like teeth, the resting lid line read as a frown, and a stray spike showed at the hem.'],
      ['v3', 'Lighter, thinner rim, no lid line at rest, mittens only when he uses them, shorter boots. Concerned brows now tilt the right way.'],
    ],
    scores: { before: [2.5, 3, 4, 3, 2, 3.5, 4], after: [3.5, 4, 5, 4, 3.5, 4, 4] },
    risks: 'Pointed knitted hoods pull toward garden gnomes, Smurfs and Christmas elves. A pale face in a dark hood opening can look ghostly. Flying is the least natural of the three: he would float, and the helpers become little ghosts.',
  },
];

const rubric = ['Appeal', 'Uniqueness', 'Readable at 36 pt', 'Personality', 'Fits the brand', 'Animatable', 'Light and dark'];
const rubricHelp = [
  'Would you like to look at him every day? Shape, proportion, charm.',
  'Could you mistake him for someone else\'s mascot?',
  'At helper size, as a solid silhouette and in colour.',
  'Can he be dry, curious, sleepy, unsure, without a word?',
  'A good neighbour who is handy. Grown-up, never sugary. Works with helpers, flight and his own cursor.',
  'Parts with clear pivots, few overlaps, gestures that are blends of the same parameters.',
  'Holds up on both, without an outline.',
];

const total = (a) => a.reduce((x, y) => x + y, 0);

function corner(c, dark) {
  const st = S(c);
  const bg = dark
    ? 'linear-gradient(160deg,#2B2745 0%,#1A1828 60%,#272036 100%)'
    : 'linear-gradient(160deg,#DCE3F2 0%,#EDE6F2 55%,#F6E9DE 100%)';
  const win = dark ? '#26243A' : '#FFFFFF', ink = dark ? '#CFCAE6' : '#3A3550', line = dark ? '#3A3656' : '#E6E3EE';
  return `<div class="desk" style="background:${bg}">
    <div class="win" style="background:${win};border-color:${line};color:${ink}"><div class="bar"><i></i><i></i><i></i></div>
      <div class="lines"><span style="background:${line};width:70%"></span><span style="background:${line};width:55%"></span><span style="background:${line};width:62%"></span><span style="background:${line};width:40%"></span></div></div>
    <div class="helper" style="left:236px;top:96px">${fig(c, { ...st.flying, small: true, extras: [] }, 40, TIGHT)}</div>
    <div class="helper" style="left:150px;top:150px">${fig(c, { ...st.working, small: true, cursorAt: null, extras: [] }, 36, TIGHT)}</div>
    <div class="bubble" style="background:${win};color:${ink};border-color:${line}">Done. Dentist, tomorrow at nine.</div>
    <div class="milo">${fig(c, st['quietly proud'], 132, TIGHT)}</div>
  </div>`;
}

function conceptSection(k, i) {
  const { c, key, versions } = k;
  const st = c.states;
  const letter = 'ABC'[i];
  const hero = `<div class="hero">
    <figure>${fig(c, { turn: 0 }, 300)}<figcaption>front</figcaption></figure>
    <figure>${fig(c, {}, 300)}<figcaption>three-quarter, his resting pose</figcaption></figure>
    <figure>${silhouette(c, {}, 300)}<figcaption>silhouette</figcaption></figure></div>`;
  const states = (bg, fg, list) => `<div class="grid" style="background:${bg};color:${fg}">${list
    .map(([n, p]) => `<figure>${fig(c, p, 132)}<figcaption>${n}</figcaption></figure>`)
    .join('')}</div>`;
  const small = ['idle', 'listening', 'working', 'flying', 'happy', 'concerned', 'sleepy', 'confused'];
  const sizes = (bg) => `<div class="sizes" style="background:${bg}">${fig(c, {}, 300, TIGHT)}${fig(c, {}, 132, TIGHT)}<div class="smalls">${small
    .map((n) => fig(c, { ...S(c)[n], small: true, extras: [], cursorAt: null }, 36, TIGHT))
    .join('')}</div></div>`;
  const sil = `<div class="smalls sil">${small.map((n) => silhouette(c, { ...S(c)[n], small: true }, 36, '#26222F', TIGHT)).join('')}</div>`;
  const strip = strips[c.name];
  const film = `<h4>${strip.title}</h4><div class="strip">${strip.frames
    .map(([p, label], j) => `<figure>${fig(c, p, 150)}<figcaption>${j + 1}. ${label}</figcaption></figure>`)
    .join('<span class="arrow">›</span>')}</div>`;
  const history = `<div class="history">${k.critique
    .map(([v, text]) => {
      const file = `${key}-${v}.png`;
      const img = existsSync(join(pngDir, file))
        ? `<a href="milo-character/${file}"><img src="milo-character/${file}" alt="${c.name} ${v} sheet" loading="lazy"></a>`
        : `<div class="noimg">quick draft, no sheet kept</div>`;
      return `<div class="step">${img}<div><b>${v}</b> ${text}</div></div>`;
    })
    .join('')}</div>`;
  const scoreRows = rubric
    .map((r, j) => `<tr><td>${r}</td><td>${k.scores.before[j]}</td><td><b>${k.scores.after[j]}</b></td></tr>`)
    .join('');
  return `<section id="${key}">
    <h2>${letter}. ${c.name}</h2>
    <p class="pitch">${k.pitch}</p>
    <ul class="sig">${k.signatures.map((s) => `<li>${s}</li>`).join('')}</ul>
    ${hero}
    <h3>States at 132 pt</h3>
    ${states(LIGHT, '#3A3550', st)}
    ${states(DARK, '#CFCAE6', st.slice(0, 6))}
    <h3>300, 132 and 36 pt, light and dark</h3>
    ${sizes(LIGHT)}${sizes(DARK)}${sil}
    <h3>A gesture</h3>
    ${film}
    <h3>In the corner</h3>
    <div class="corners">${corner(c, false)}${corner(c, true)}</div>
    <h3>How it got here</h3>
    ${history}
    <div class="scorebox"><table><tr><th>Rubric</th><th>first</th><th>last</th></tr>${scoreRows}<tr class="sum"><td>Total of 35</td><td>${total(k.scores.before)}</td><td><b>${total(k.scores.after)}</b></td></tr></table>
    <p><b>Risks.</b> ${k.risks}</p></div>
  </section>`;
}

const swatches = [
  ['Milo lavender', '#9688D6', 'body, his cursor, the main colour'],
  ['Light lavender', '#C6BCF0', 'highlights, the body in dark mode'],
  ['Deep lavender', '#5E4FA4', 'shadows, wings, text on light'],
  ['Ink', '#1E1730', 'eyes, the darkest line'],
  ['Cream', '#FBF3E8', 'belly, bubbles, paper'],
  ['Marigold', '#F0B649', 'the scarf: accent, "done" sparks, the new dot'],
  ['Marigold deep', '#C98526', 'scarf shade, accent text on light'],
  ['Beak tan', '#E6B274', 'beak, feet'],
  ['Blush', '#EE9AA6', 'only when he is pleased'],
];

const stateTable = [
  ['idle', 'Resting three-quarter toward the screen centre, eyes 75% open, slow breath (3.6 s). Eyes follow the cursor, then lose interest.', 'turn -0.2, lid 0.2, breath'],
  ['listening', 'Leans toward you, eyes open wider, brows up a little, tail lifts. A nod on new words.', 'lean, headTilt, lid 0.1, brow +0.5, tail +10'],
  ['thinking', 'Looks up and away, one brow higher, tail low and still. Steady, never frantic. Only while work really runs.', 'gaze up-left, browL +0.9, tail -6'],
  ['speaking', 'Beak opens with the voice level, eyes glance at his bubble and back.', 'mouth = level, lid 0.16'],
  ['working', 'Scarf tossed over his shoulder, focused lids, brows down a touch, his cursor out.', 'scarfToss 1, lid 0.36, browTilt -0.3'],
  ['flying / pointing', 'Wings up in a V, scarf streams behind. Pointing: one open wing, primaries as fingers.', 'fly 1, wingOpen, lean'],
  ['happy', 'Smiling arched eyes, small hop, tail up and fanned, a little blush. Earned, not default.', 'lower 0.9, tailFan 1, lift'],
  ['concerned', 'Brows tilt in and up, leans back, eyes a little smaller, tail drops.', 'browTilt +0.9, lean +5, tail -14'],
  ['sleepy', 'Eyes shut, scarf pulled over the beak, body settles, breathing slows to 5.5 s.', 'lid 1, scarfUp 1, squash -0.05'],
  ['confused', 'Head tilts, one brow up, one eye smaller. Then he says what he missed.', 'headTilt 11, browR +0.9, eyeScaleL 0.8'],
  ['quietly proud', 'A small nod, eyes close in a smile, chest puffs, tail fans once. One spark, no confetti.', 'lower 1, squash +0.035, tailFan'],
];

const micro = [
  ['Peeks at the cursor', 'Eyes lead, the head follows 120 ms later with a small tilt. Loses interest about 3 s after the pointer stops.'],
  ['Scarf toss', 'Starting a job: looks down, squashes, tosses the loose end over his shoulder. It means "on it" without a word.'],
  ['Tail tap', 'Waiting for a yes: the tail ticks like a slow metronome, about once a second, and rests after six ticks.'],
  ['Proud nod', 'A job finished: one nod, eyes close into arches, tail fans for a beat. No hop, no confetti.'],
  ['Pencil note', 'Told to remember something: takes the pencil from his scarf, two small scribbles in the air, tucks it back.'],
  ['Brow lift', 'Didn\'t catch it: one brow goes up and stays until you answer.'],
  ['Ruffle and settle', 'Back in the corner after flying: a quick shake from tail to head, then a settle on his feet.'],
  ['Scarf pull at night', 'Late or alone for 10 minutes: a yawn, pulls the scarf over his beak, tail lowers, breathing slows. Hover and one eye opens first.'],
  ['Hop-turn', 'You bring a window up on the other side: a small anticipation dip, a hop, and he faces it.'],
  ['Glance at the bubble', 'While he talks his eyes drop to his own bubble now and then, the way you check your notes.'],
];

const css = `
  :root{--ink:#2B2740;--muted:#5D5775;--paper:#FBFAFD;--rule:#E4E0EE;--lav:#5E4FA4;--mari:#C98526}
  *{box-sizing:border-box} body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif}
  main{max-width:1180px;margin:0 auto;padding:40px 28px 80px}
  h1{font:700 34px/1.15 -apple-system,"SF Pro Display",system-ui;margin:0 0 8px;letter-spacing:-.01em}
  h2{font:700 26px/1.2 -apple-system,"SF Pro Display",system-ui;margin:56px 0 8px;padding-top:18px;border-top:1px solid var(--rule)}
  h3{font:600 15px/1.3 -apple-system,system-ui;margin:28px 0 10px;color:var(--muted);text-transform:none}
  h4{font:600 14px/1.3 -apple-system,system-ui;margin:6px 0 10px}
  p{max-width:760px} .lede{font-size:17px;color:var(--muted);max-width:820px}
  nav a{margin-right:14px;color:var(--lav);text-decoration:none;font-weight:600}
  figure{margin:0;display:flex;flex-direction:column;align-items:center} figcaption{font-size:12px;opacity:.75;margin-top:2px;text-align:center}
  .hero{display:flex;gap:14px;flex-wrap:wrap} .hero figure{background:${LIGHT};border-radius:16px;padding:6px 8px 10px}
  .grid{display:flex;flex-wrap:wrap;gap:6px;padding:10px;border-radius:16px;margin-bottom:8px}
  .sizes{display:flex;align-items:flex-end;gap:22px;padding:14px 20px;border-radius:16px;margin-bottom:8px}
  .smalls{display:flex;gap:10px;align-items:flex-end} .sil{padding:4px 20px 0}
  .strip{display:flex;align-items:center;gap:2px;background:${LIGHT};border-radius:16px;padding:10px;overflow-x:auto} .arrow{font-size:28px;color:#B3ABCF}
  .strip figure{width:180px}
  .corners{display:flex;gap:14px;flex-wrap:wrap}
  .desk{position:relative;width:560px;height:300px;border-radius:14px;overflow:hidden}
  .win{position:absolute;left:28px;top:30px;width:330px;height:210px;border-radius:10px;border:1px solid;box-shadow:0 10px 30px rgba(30,20,60,.15)}
  .bar{height:26px;display:flex;gap:6px;align-items:center;padding-left:10px} .bar i{width:10px;height:10px;border-radius:50%;background:#E3DFEC}
  .lines{padding:14px 18px;display:flex;flex-direction:column;gap:12px} .lines span{height:9px;border-radius:5px;display:block}
  .helper{position:absolute} .milo{position:absolute;right:10px;bottom:4px}
  .bubble{position:absolute;right:120px;bottom:118px;font-size:13px;padding:8px 12px;border-radius:14px;border:1px solid;box-shadow:0 6px 18px rgba(30,20,60,.12)}
  .history{display:flex;flex-direction:column;gap:12px} .step{display:flex;gap:14px;align-items:flex-start}
  .noimg{width:240px;height:60px;border:1px dashed var(--rule);border-radius:10px;font-size:12px;color:var(--muted);display:flex;align-items:center;justify-content:center;flex:none}
  .step img{width:240px;border-radius:10px;border:1px solid var(--rule)} .step div{max-width:760px}
  .scorebox{display:flex;gap:28px;align-items:flex-start;margin-top:18px;flex-wrap:wrap} .scorebox p{max-width:560px;margin:0}
  table{border-collapse:collapse;font-size:14px} td,th{padding:5px 12px;border-bottom:1px solid var(--rule);text-align:left} th{color:var(--muted);font-weight:600}
  tr.sum td{border-bottom:none;padding-top:8px}
  .pitch{font-size:16px} .sig li{margin-bottom:4px;max-width:820px}
  .swatches{display:flex;flex-wrap:wrap;gap:10px} .sw{width:122px;font-size:12px} .sw b{display:block;height:46px;border-radius:10px;margin-bottom:4px;border:1px solid rgba(0,0,0,.06)}
  .compare{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end} .compare figure{background:${LIGHT};border-radius:16px;padding:8px}
  .rec{background:#F3EFFB;border:1px solid #DCD4F3;border-radius:16px;padding:18px 22px;margin-top:20px}
  .bible{columns:2;column-gap:36px} .bible>div{break-inside:avoid;margin-bottom:14px}
  @media (max-width:900px){.bible{columns:1}}
`;

const lineup = (bg, fg) => `<div class="compare" style="background:${bg};padding:12px;border-radius:18px">${concepts
  .map((k) => `<figure style="background:transparent;color:${fg}">${fig(k.c, {}, 250)}<figcaption>${'ABC'[concepts.indexOf(k)]}. ${k.c.name}</figcaption></figure>`)
  .join('')}</div>`;

const scoreTable = `<table><tr><th>Rubric</th>${concepts.map((k) => `<th>${k.c.name}</th>`).join('')}<th>What it asks</th></tr>${rubric
  .map((r, j) => `<tr><td>${r}</td>${concepts.map((k) => `<td>${k.scores.after[j]}</td>`).join('')}<td style="color:var(--muted)">${rubricHelp[j]}</td></tr>`)
  .join('')}<tr class="sum"><td>Total of 35</td>${concepts.map((k) => `<td><b>${total(k.scores.after)}</b></td>`).join('')}<td></td></tr></table>`;

const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Milo, one character</title><style>${css}</style></head><body><main>
<h1>Milo, one character</h1>
<p class="lede">The skins we have (Pip, the robot, the dragon, Kit, Glow) are cute and could belong to anyone. This page replaces them with one Milo, drawn with care. Below are three directions, each drawn on a small rig of pose parameters, critiqued against the same rubric and redrawn until the obvious problems were gone. My pick is at the end.</p>
<nav><a href="#dna">Design DNA</a><a href="#wren">A. Wren</a><a href="#moth">B. Moth</a><a href="#sprite">C. Sprite</a><a href="#pick">The pick</a></nav>

<h3>The three, side by side</h3>
${lineup(LIGHT, '#3A3550')}
<div style="height:8px"></div>
${lineup(DARK, '#CFCAE6')}

<p>Every figure on this page is inline SVG produced by the same three small rigs (<code>docs/design/milo-character/src/*.mjs</code>). A state is a set of numbers on the rig: turn, lean, squash, lift, head tilt, gaze, upper and lower lids, brows, beak, wings, tail, accessory. That is how the SwiftUI version will work too, so a transition is a blend of numbers, not a swap of drawings. The reference research is in <a href="../research/character.md">docs/research/character.md</a>.</p>

<section id="dna">
<h2>Design DNA</h2>
<p>This holds for whichever direction we choose. Where it needs a concrete body it describes the wren, my pick.</p>
<div class="bible">
<div><h4>Who he is, in a body</h4><p>A small, sturdy neighbour who is good with his hands. Round where he is friendly, with one shape that sticks out with intent. He is grown-up: his eyes rest about three quarters open, so he looks calm and a bit dry, not thrilled. He smiles when something earns it. He is never sugary and never pleads.</p></div>
<div><h4>Silhouette</h4><p>Reads as one shape at 36 pt: a round body planted on the ground, plus one asymmetric feature that breaks the circle on the side away from you. For the wren that is the cocked tail, balanced by the scarf end hanging out on the other side. He sits in three-quarter view turned toward the screen centre, never flat to camera.</p></div>
<div><h4>Shape language</h4><p>Circles for the body and eyes (safe, friendly). One point, the beak, for intent. Soft rectangles only in the scarf and pencil, the "handy" things. No two big parts the same size: body, then scarf band, then eyes, then beak.</p></div>
<div><h4>Signature features</h4><p>Wren: the cocked tail, the pale brow stripes, the marigold scarf with a pencil. Each one carries a gesture (tail tap, brow lift, scarf toss), so the features are also how he acts.</p></div>
<div><h4>Light and material</h4><p>Key light from the upper left, a soft cool rim light on the right edge, ambient occlusion where he meets the ground and under the scarf, one catchlight per eye. The lids use the body's own gradient so they vanish until they move. No outlines; the rim light separates him from dark backgrounds.</p></div>
<div><h4>Motion</h4><p>Breathing all the time, everything else rare. Beyond breathing, idle motion stays under about 10% of the time and stops while you type. Eyes lead, the head follows. Every gesture gets anticipation and follow-through (the scarf and tail drag behind the body). Quieter and slower at night.</p></div>
</div>
<h3>Colour</h3>
<div class="swatches">${swatches.map(([n, c, u]) => `<div class="sw"><b style="background:${c}"></b>${n}<br><code>${c}</code><br><span style="color:var(--muted)">${u}</span></div>`).join('')}</div>
<p>Lavender stays Milo's colour, made a little greyer and warmer than Pip's so it reads as a bird and not as candy. Marigold is the single accent and lives on the scarf, so the theme's accent colour (badges, "done" sparks) is literally a piece of him.</p>
<h3>How he shows each state</h3>
<table><tr><th>State</th><th>What the body does</th><th>Rig numbers</th></tr>${stateTable.map(([a, b, c]) => `<tr><td><b>${a}</b></td><td>${b}</td><td><code>${c}</code></td></tr>`).join('')}</table>
<h3>Micro-behaviours</h3>
<p>Scheduled with variety, never on a fixed loop, never two at once, and much rarer at night.</p>
<table>${micro.map(([a, b]) => `<tr><td><b>${a}</b></td><td>${b}</td></tr>`).join('')}</table>
<h3>The rubric</h3>
<p>Each criterion scored 1 to 5 on the last version of each concept. The first and last scores for each concept are in its section.</p>
${scoreTable}
</section>

${concepts.map(conceptSection).join('')}

<section id="pick">
<h2>The pick: the wren</h2>
<div class="rec">
<p><b>I'd build the wren.</b> He scores highest on the two things that matter most for Milo: he fits the product, and he is the easiest to make feel alive.</p>
<p>He fits because the story already exists. Milo flies to the window he works in, sends out small helpers, and has his own cursor. A bird does all of that without explanation, and at 36 pt a helper still reads as Milo: a lavender ball with a marigold band. Wrens also nest in the nooks of houses, which is where he lives.</p>
<p>He feels alive because each signature feature is also a gesture. The scarf toss says "on it". The scarf over the beak says goodnight. The tail tap says "I'm waiting for your yes". The brow lift says "hm?". Those map one to one onto states the app already sends, so the personality comes from the rig rather than from extra animation on top. The brow stripes give him the dry, a-little-amused face that CHARACTER.md describes better than big glossy eyes do.</p>
<p>The moth is the most original of the three and I like it a lot, but insects are a gamble with the people Milo is for, and his wings don't fit the corner. The sprite has the best silhouette, but knitted pointed hoods lead to gnomes and elves, and a face in a hood can look ghostly.</p>
<p>What I would carry over: the sprite's knitted texture is already on the scarf. The moth taught me that the brows have to carry the emotion, and the wren's brow stripes do that.</p>
<p><b>Open questions for you.</b> Keep the pencil, or let the scarf alone carry "handy"? Is marigold right, or should the scarf be a deeper rust? And the name of the bird never shows in the app, so he stays "Milo", not "Milo the wren".</p>
</div>
</section>
</main></body></html>`;

writeFileSync(page, html);
console.log(page, Math.round(html.length / 1024) + ' KB');

// overview PNGs for the report
const shot = (body, file, w, h) => render(`<!doctype html><html><head><meta charset="utf-8"><style>${css} body{background:#fff}</style></head><body style="padding:16px;width:${w}px">${body}</body></html>`, join(pngDir, file), w + 32, h);
shot(`${lineup(LIGHT, '#3A3550')}<div style="height:8px"></div>${lineup(DARK, '#CFCAE6')}`, 'lineup.png', 820, 640);
shot(`<div class="corners" style="flex-direction:column">${concepts.map((k) => `<div style="display:flex;gap:12px">${corner(k.c, false)}${corner(k.c, true)}</div>`).join('')}</div>`, 'corners.png', 1140, 980);
shot(concepts.map((k) => {
  const strip = strips[k.c.name];
  return `<h4>${k.c.name}: ${strip.title}</h4><div class="strip">${strip.frames.map(([p, label], j) => `<figure>${fig(k.c, p, 150)}<figcaption>${j + 1}. ${label}</figcaption></figure>`).join('<span class="arrow">›</span>')}</div>`;
}).join(''), 'gestures.png', 1040, 820);
console.log('pngs written');
