# Milo homepage: research notes and design plan

## What to take from the best product sites (looked at 2026-10-30)

- **Granola**: the product's own window is the hero picture, not an illustration. One big headline, a two-line subhead, one button. Copy it: every Milo section shows a small, real-looking Mac window, built in HTML so it stays sharp at 2x.
- **Linear**: each feature gets a short headline, one sentence, and a working-looking piece of UI. No paragraphs. Copy the rhythm: headline, one line, demo.
- **Things**: calm. One object, lots of air, small precise shadows. The craft is in the icon. Copy the restraint everywhere except Milo.
- **Raycast**: the download button sits with a quiet line under it that says what you need ("macOS ... required"). Copy it: the requirements line under the waitlist button.
- **Arc** (the "farewell" letter and Dia page): a human, plain voice, written like a person talking. The FAQ reads like answers, not policy. Copy the voice in the FAQ.
- **Duolingo**: the character is the brand. Duo shows up in a different pose in every section, doing what that section is about, and reacts to you. Copy it: Milo listens in the talk demo, tosses his scarf when he starts the spreadsheet, ticks his tail while he waits for a yes, sleeps when you leave.
- **Wispr Flow** (timed out in the headless browser, from memory): the demo is text arriving in a real app as someone speaks. Copy it for dictation, with the "um"s visibly dropped.

What not to take: dark "developer" heroes (Raycast, Linear) read as technical and cold to the audience here, and Granola's collage textures fight a character.

## Design plan

**Idea.** The page is a desk, and Milo lives in its corner. He starts big in the hero, flies into the bottom-right corner as you scroll (exactly where he lives on a Mac), watches the demos from there, and flies back out to sit in the final waitlist section. One persistent character is the bold thing. Everything else is quiet.

**Colour** (from `Theme.swift`, skin Pip, and the wren rig):

| Name | Light | Dark | Use |
|---|---|---|---|
| paper | `#F5F3FD` | `#17142A` | page background, a lavender white, not cream |
| ink | `#2B2454` | `#EDEBFF` | text |
| lavender | `#6B5CBF` | `#B8ADF2` | links, Milo's cursor, outline, focus |
| marigold | `#E8912E` / scarf `#F0B649` | `#FAB861` | Milo's scarf, the one warm accent, fills only |
| card | `#FFFFFF` | `#211D38` | mock windows |
| mist | `#E7E3F8` | `#2A2546` | rules, quiet fills |

**Type.**
- Display: Fraunces, with the SOFT axis at 100. Round, soft serif terminals that echo a round bird, set large and tight.
- Text: Atkinson Hyperlegible Next, made by the Braille Institute for readers with low vision. The audience is people in their sixties, so body text is 19 to 20 px.
- No all-caps labels, no eyebrows over headings, no monospace labels, no arrows on buttons.

**Layout.** Left-aligned text column (max 34 rem) beside a demo on wide screens, stacked on phones. Sections are not numbered, because they aren't a sequence.

```
[nav: wren head  Milo      How he works  Privacy  Pricing  FAQ   (theme)  [Join the waitlist]]

 Just tell Milo.                               (   Milo, big, alive   )
 He's a small coworker ...                       "On it."
 [Join the waitlist]  See him work
 For Macs with Apple silicon ...

 Hold a key and say it.        [ key: hold to talk ]  [Milo listening, live words pill]
 Talk instead of typing.       [ Mail window, words arriving ]
 He works where you can see.   [ Excel window, lavender outline, his cursor + tag ]
 ...                                                                   (corner Milo)
```

**Principles.**
1. Show, don't tell: every feature is a small demo that runs when you reach it and can be replayed.
2. Milo behaves the way CHARACTER.md says: he watches, keeps quiet, and never talks just to look alive.
3. Trust shows in the page itself: no cookies, no tracking, no third-party requests, honest about what goes to the internet and what isn't built yet.
4. One warm accent (marigold) and only on Milo's things: his scarf, the Plus plan, the record dot is red.

## Review passes

Every section at 390, 1440 and 2560 px, light and dark, with reduced motion so demos show their finished state (`bun run shots <pass>`), plus things that only exist in motion (`bun run moments <pass>`: Milo flying, in the corner, the pricing remark, asleep, waving, demos halfway, focus rings).

- `p1-before/`: the first full build.
- `p2/`: after the first round of fixes.
- `p3-after/`: after the second round, with wren v4.
- `p4/`: the cuter wren from track 12. The best shots are listed in `site/README.md`.
- `p5/`: brought up to date with ADRs 24 to 32 (2026-10-31): the done card in the hero and a quick-things demo, opening, undo, auto mode, the step under the outline, meeting notes by voice. 390 and 1440 only. `p5/moments/` has the hero card, the deck fanned out, an undo and the outline's caption mid-run.

- `p6/`: writing where you are, the voice on the Mac and the smaller features (2026-10-31): `Write.astro`, `Local.astro`, `More.astro`, a new hero lede and pills. 390 and 1440. The README's pictures in `assets/readme/` come from the same pass.
- `p8/`: the open-source launch (2026-10-31). Pricing went, the waitlist became `Get.astro`, the nav, hero, FAQ and footer point to GitHub. Nav, hero, Get and FAQ at 390 and 1440.

### Pass 8, free and open source

- Milo launches as open source first, so the Plus price and the waitlist went. The last section, "Free, and yours.", shows the one-line install with Copy, "Get it on GitHub" and how to install. A card under it, "Maybe later", asks who'd want a hosted Milo with nothing to set up, and keeps the old honest form: it sends nothing and offers an email.
- The corner Milo's remark about the prices went with them.
- First shots: on a phone the one-line command widened the grid's only column past the screen, so the whole section was clipped on the right. The grid's column is now `minmax(0, 1fr)` and the command scrolls inside its box.

### Pass 6, what was added and checked

- ADR 33 (`<write>`) got its own section after Talk: Anna's email as the context, the answer landing in the reply in one piece with a marigold flash, a `written` card ("In Mail", the app's text-cursor symbol) and the brain's own line "It's in Mail, have a look." Beside it, the six steps of copying into a chatbot get crossed out.
- The voice moved to Pocket TTS on the CPU, so "His voice is made online too" went from the FAQ and Trust. The local section's numbers come from the code: ½ s is the dictation test's paste limit (1 s after more than 20 s of speech, which the stat says), 7x is Pocket on an M3 (`adapters/tts/pocket.py`).
- First shots: the strike-through ran the full width of each step (now on the text only), Anna's email was clipped at the left edge, the small-things grid had holes at 4 columns, and the travelling dot drew over the icons. All fixed.
- Also on the page now: undo later, learning dictation words, hands-free, What's this?, routines, the two languages.

### Pass 5, what the site said against what Milo does now

- The hero's "Done. Dentist, Thursday at nine." became the brain's own line, "Dentist, Thursday at 9 am. It's in." (`quick_words.py`), and the calendar's today moved to Monday so "Thursday" is what the brain would say (it says "today" for the same day and the full date a week ahead).
- `:root:not([data-milo='hero'])` hid the hero's words pill until the script first set `data-milo`, so with reduced motion the pill never showed. It now applies only once the attribute is set.
- In the deck, `[data-behind]` outranked `.is-open`, so the cards behind stayed blank when fanned out.
- "Lunch with Anna" didn't fit on a card (the app truncates at the same width), so the demo adds a haircut.
- Money moved from "never" to "asks, and only a click counts" in ADR 23, so "no bank transfers" went from Trust and the FAQ.

### Pass 1, against the details list

- Scoped CSS didn't reach anything a script creates (chat bubbles, transcript lines, step lists) or the `<milo-character>` root of a child component, so the phone chat was unstyled and several Milos were the wrong size. Fixed with `:global()` on those selectors.
- The pricing check marks were invisible for the same reason.
- The question bubble in "asks first" covered the email it asked about. It now sits beside Milo, under the window.
- The hero bubble kept a stale line when Milo flew back to the hero, and with reduced motion his hero line followed him into the corner. He now hushes when he leaves the hero and says his line again when he's back.
- The end slot was empty without scripts. It now has a server-drawn Milo that the flying one replaces.
- Sections were too far apart (up to 18 rem between them). Cut to about 14 at most.
- Edit and Forget in the memory window were at 25% opacity, too faint to read. They're now always readable and turn lavender on hover.
- The words pill in the talk demo was greyed out when idle, failing contrast. It's now a light card when idle.
- Two sets of "z"s when asleep (the rig's and the CSS ones). The rig's are only used for the footer's static Milo now.
- Chrome can't capture more than 16k px in one go, so the overview shots are now taken at 1x.

### Pass 2

- On phones the spreadsheet's minimum width pushed the whole section past the screen, where `overflow-x: clip` hid it. Grid items can shrink now and the sheet tightens below 30 rem. Checked for overflow at 360, 390, 768, 1024, 1280, 1920 and 2560.
- The corner Milo covered text on phones. He's 64 px there now and steps out of the way while you scroll, coming back a second after you stop.
- He landed in the end section only when it was half off the screen. He lands earlier now.
- The spreadsheet's step list spread its lines over the whole box. Fixed.
- The hero calendar was cramped on phones. Six rows instead of eight, a smaller face on phones.
- Lighthouse accessibility was 90: `aria-label` on plain spans, Milo's cursor tag at 4.3:1 contrast, and list items under a `tabpanel` list. All fixed (100).
- Every server-drawn Milo redrew itself once on load for nothing, which showed up as main-thread time. The first redraw is skipped now unless something moves, and helpers keep their small drawing when they blink.
- "Ask us. A person answers." had nowhere to write to. It's a link now.
- Plus's corners on phones, plan headers aligned to the top, a bigger hero headline on large screens.
- Copy: removed mid-sentence colons and the one pair of brackets (unslop pass).

### Pass 4, the cuter wren

The app's wren changed after track 12: a fluffy three-feather tuft, soft lavender brows instead of white stripes, big low eyes with two catchlights and a sparkle, pink cheeks, a rounder body and a slimmer, shorter scarf. The JS rig in `docs/design` was still v4, so `src/character/wren.js` is now a port of `WrenRig.swift`, and the motion follows `WrenMotion.swift`: a spring per number, the app's moves (hop, happy wiggle, fluff-up, perk, flinch, double take, ruffle...) played on pose changes, and the scarf, tail, head and tuft thrown about by his motion. The tuft perks up when he listens, lies flat when he sleeps and fluffs up when he's surprised.

- The wave first used his right wing, which opens over his tail and got lost. It uses the left one now, clear of the tail.
- Halfway through the wave his eyes sat between open and smiling. The wave now closes them all the way into smile arches.
- The yawn left his lids 0.4 lower when it ended, which popped. Every move now ends at rest.
- The phone's chat avatar showed him sunk into the bottom of the circle. His face is in the middle now, tuft to feet inside.
- The icon crop is wider so the tuft and tail fit (`30 34 152 152`); the share card shows him bright-eyed, tuft up.
- An idle Milo stops redrawing once he settles, as before. Only the hero Milo, who talks in a loop, keeps animating.

