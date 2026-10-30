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
