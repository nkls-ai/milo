# Milo's homepage

A static page that introduces Milo to people who don't use AI yet. Astro on Bun, no tracking, no cookies, nothing loaded from anyone else (the fonts ship with the page). Nothing here is deployed.

```sh
bun install
bun run dev        # http://localhost:4321, stop it with: bun run dev:stop
bun run build      # static site in dist/
```

Astro 7 wants a newer Node than some Macs have, so the scripts run it on Bun's runtime (`bun --bun astro`).

## How it's put together

- `src/character/` is the one place that decides how Milo looks. `wren.js` is the app's wren (`app/Sources/MiloKit/Views/Wren/WrenRig.swift`) ported to SVG: the young, round wren with a fluffy three-feather tuft, soft lavender brows, big eyes with two catchlights and a sparkle, pink cheeks and a slim scarf. `index.js` wraps it as `rig`: the poses from `WrenDirector.swift`, the moves from `WrenClips` (hop, happy wiggle, fluff-up, perk, nod, tail tick, scarf toss, flinch, double take, ruffle, wave, yawn and more), which moves a change of pose calls for, alt text and the gaze. To try another design, write a rig with the same shape and change the import there.
- `src/character/element.js` is `<milo-character>`, the app's motion (`WrenMotion.swift`): every pose number on its own spring, moves laid on top as curves, the scarf, tail, head and tuft thrown about by the body's motion, blinks, wingbeats and idle habits. It redraws the SVG only while something moves.
- `src/components/Character.astro` draws Milo on the server in one pose, so he's there before any script runs. Every Milo on the page goes through it.
- `src/scripts/milo.ts` is the Milo who lives on the page: he flies from the hero into the bottom-right corner as you scroll, follows your pointer with his eyes, steps aside when a demo has its own Milo, notices the prices, falls asleep after 45 seconds alone, waves when you come back, and flies out to sit in the waitlist section at the end.
- `src/components/demos/` are the eight demos. `src/scripts/demo.ts` plays each one once when you reach it, with "Play again", and with reduced motion jumps straight to the finished state.
- `src/site.ts` holds what changes before launch: the contact address (a placeholder, `hello@milo.example`) and the Plus price.
- Colours come from the app's Pip theme (`app/Sources/MiloKit/Theme.swift`) and the wren's scarf. Type is Fraunces (soft) for headings and Atkinson Hyperlegible Next for text, picked for readers with weaker eyes.

The waitlist form doesn't send anything. It says so under the field, and on submit it offers an email instead.

## Tools

```sh
bun run assets       # favicon, app icons and the share card, drawn from the rig into public/
bun run shots p4     # every section at 390, 1440 and 2560, light and dark, into review/p4 (needs bun run dev)
bun run moments p4   # Milo flying, in the corner, asleep, waving, demos halfway (needs bun run dev)
bun run lighthouse   # serves dist/ with gzip and runs Lighthouse with the local Chrome
bun scripts/compress-review.ts review/p4   # PNG to WebP before committing
```

The screenshot tools use the Chrome in /Applications.

## Review

`review/NOTES.md` has the research notes, the design plan and what each review pass found. Lighthouse, measured locally on 2026-10-30 against `dist/` served with gzip:

| | Performance | Accessibility | Best practices | SEO | LCP | CLS |
|---|---|---|---|---|---|---|
| Mobile | 100 | 100 | 100 | 100 | 1.1 s | 0 |
| Desktop | 100 | 100 | 100 | 100 | 0.3 s | 0 |

The best shots:

- `review/p4/top-1440-light.webp` and `top-1440-dark.webp`: the hero
- `review/p4/moments/flying-1440-light.webp`: Milo flying into the corner
- `review/p4/moments/talk-holding-1440-light.webp`: listening, his tuft perked up
- `review/p4/moments/work-mid-1440-light.webp`: his cursor and outline in the spreadsheet
- `review/p4/moments/pricing-remark-1440-dark.webp`: he notices the prices and fluffs up
- `review/p4/moments/final-1440-light.webp`: he lands in the waitlist section
- `review/p4/moments/asleep-1440-light.webp` (tuft flat) and `waving-1440-light.webp`
- `review/p4/helpers-1440-dark.webp`: the small helper Milos
- `review/p4/_full-390-light.webp` and `_full-2560-dark.webp`: the whole page
- The old wren against the new: `review/p3-after/top-1440-light.webp` against `review/p4/top-1440-light.webp`
