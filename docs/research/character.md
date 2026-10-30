# Milo character: research brief

Input for the designer drawing Milo in SVG and for whoever rigs him in SwiftUI. Milo is about 132 pt in the bottom-right corner, his helpers about 36 pt. Every link is a page I opened in October 2026. Unlinked points are common animation practice or my own suggestion.

## 1. Duolingo's Duo

I found no Duolingo post about a 2023 redesign. The relevant work is spread across these posts.

- **Silhouette first.** "If the overall shape is not appealing, then the details within that shape can't compliment it successfully." Duo's default angle is a "slight quarter-turn" ([Reshaping Duo](https://blog.duolingo.com/reshaping-duo/)).
- **Four parts.** Duo is "basically just a body with wings": geometric construction, big expressive eyes, a unique body shape, detached feet ([Building character](https://blog.duolingo.com/building-character/)).
- **Few shapes, pushed hard.** "Very few cleverly placed vector shapes", key details exaggerated "almost to the point of caricature", and no flat, pointy shapes ([Shape language](https://blog.duolingo.com/shape-language-duolingos-art-style/)).
- **Mouths run beside the body.** 20+ mouth shapes per character. Mouth states play alongside body states, and phoneme timings trigger the state machine in sync with audio ([Visemes](https://blog.duolingo.com/world-character-visemes)).
- **Idle variety, honest eyes.** Lily's 8 head and 8 body idles combine into 64+ variations, using separate nested artboards. A processing delay plays as pondering. The team reduced her eye openness because wide eyes read as too happy ([Rive case study](https://rive.app/blog/duolingo-s-ai-powered-video-call-brings-lily-to-life)).
- **Unhinged is a marketing voice.** The chaotic Duo lives on TikTok, and even there the limit is "We never want Duo to be that pushy friend that makes you hate your existence" ([Digiday](https://digiday.com/marketing/how-duolingo-is-using-its-unhinged-content-with-duo-the-owl-to-make-people-laugh-on-tiktok/)). Milo lives inside the product, so he gets the calm version.

## 2. Other product characters

- **Freddie always winks**, because he has a great attitude, and the files must not be modified ([Mailchimp brand assets](https://mailchimp.com/about/brand-assets/)). The 2018 Collins rebrand used "a more simplified Freddie" ([It's Nice That](https://www.itsnicethat.com/news/mailchimp-collins-brand-system-graphic-design-270918)). One fixed signature beats a large expression set.
- **GitHub keeps Mona out of the way.** "Less is more", never interrupt the user flow, never use mascots for money, security, support, apologies or crises ([GitHub brand](https://brand.github.com/graphic-elements/mascots)).
- **Headspace grew past the smile.** The 2024 rebrand added "a range of faces expressing a range of emotions beyond a smile", including stress and sadness ([It's Nice That](https://www.itsnicethat.com/articles/italic-studio-headspace-graphic-design-project-250424)).
- **Animoji is mostly eyes and brows.** Apple quoted "more than 50 different muscle movements" ([Emojipedia](https://blog.emojipedia.org/apples-new-animoji)). Of ARKit's 52 blend shapes, 14 are eye and 5 are brow channels, each 0 to 1 ([Apple](https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapelocation)).
- **Desktop pets react, then leave you alone.** Neko chases the cursor and falls asleep when left idle ([Wikipedia](https://en.wikipedia.org/wiki/Neko_(software))). eSheep walks the screen and drops onto the taskbar, all from one XML animation file ([desktopPet](https://github.com/rdavydov/desktopPet)).
- **Finch never scolds.** The bird celebrates finished tasks and, unlike a Tamagotchi, can't die from neglect ([Engadget](https://www.engadget.com/apps/this-self-care-virtual-pet-is-helping-me-get-my-act-together-160027169.html)). Take the no-guilt behaviour, not the kawaii look Milo is replacing.

## 3. What not to do

- **Clippy interrupted.** "It looks like you're writing a letter" became the emblem. Microsoft turned it off by default in Office XP and removed it in Office 2007 ([Wikipedia](https://en.wikipedia.org/wiki/Office_Assistant)).
- **Clippy guessed intent and acted on it.** It grew from Microsoft Research's Lumière work on Bayesian guesses about user goals ([Horvitz et al.](https://erichorvitz.com/lumiere.htm)). Horvitz's 1999 principles ask agents to weigh "uncertainty about a user's goals", "the status of a user's attention", and "minimizing the cost of poor guesses" ([CHI 99 paper](https://erichorvitz.com/chi99horvitz.pdf)).
- **Users must stay in control.** Luke Swartz's Stanford thesis, "Why People Hate the Paperclip", concluded agents should leave users feeling "in control" and follow "human rules of etiquette". Clippy did neither ([Harvard Crimson](https://www.thecrimson.com/article/2005/4/28/what-not-to-do-with-a/)). I could not find the thesis text.
- **A face raises expectations.** Alan Cooper called Clippy a "tragic misunderstanding" of Nass and Reeves' finding that people treat computers as social actors ([Wikipedia](https://en.wikipedia.org/wiki/Office_Assistant)). A face makes a wrong guess feel rude, not buggy.
- **No friendly face on a privacy problem.** BonziBuddy reset homepages without permission and was labelled spyware. The FTC fined its maker $75,000 in 2004 for collecting children's data ([Wikipedia](https://en.wikipedia.org/wiki/BonziBuddy)).

## 4. Creature design craft

- **Silhouette test.** Fill the character solid black. If you still know who it is, it works ([CG Wire](https://blog.cg-wire.com/character-shape-language/)).
- **Silhouettes in motion.** Fred Moore kept silhouettes clear even in inbetweens, using negative space between head and limbs ([Cartoon Brew](https://www.cartoonbrew.com/disney/fred-moore-and-the-moving-silhouette-82472.html)). Wings must not vanish into the body mid-gesture.
- **Shape language.** Circles read friendly, squares dependable, triangles dangerous, and good characters mix them.
- **Size contrast and asymmetry.** The usual teaching rule is one big mass, one medium, one small. A perfectly symmetric front view reads as an icon. A quarter turn or one brow higher fixes that.
- **One signature feature.** Freddie's wink, Duo's detached feet. The thing you'd draw from memory.

## 5. The 12 principles at 132 pt

Definitions follow [Wikipedia's summary of Thomas and Johnston](https://en.wikipedia.org/wiki/Twelve_basic_principles_of_animation). The applications are mine.

1. **Squash and stretch.** A few percent on landings and laughs, volume kept constant.
2. **Anticipation.** A small dip before he pops up or speaks, so the user sees it coming.
3. **Staging.** One thing moves at a time. He looks at what he is talking about.
4. **Straight ahead vs pose to pose.** Pose to pose. Each state is a key pose and code tweens.
5. **Follow through and overlap.** Tail, crest and accessory settle a beat after the body.
6. **Slow in and slow out.** Ease everything except the closing half of a blink.
7. **Arcs.** Head turns dip on an arc instead of sliding.
8. **Secondary action.** Breathing or a feather twitch, always under the main action.
9. **Timing.** A calm character moves slowly. Fast moves are for surprise.
10. **Exaggeration.** Push poses further than feels right. 132 pt is small and 36 pt is tiny.
11. **Solid drawing.** Flat SVG still needs implied volume, like a lighter belly.
12. **Appeal.** "What would be called charisma in an actor". Charisma, not cuteness.

Eye craft:

- Shawn Kelly calls the "blink every 2 seconds" rule "a very outdated concept". Blink at a thought shift, or near the middle or end of a fast head turn. "The timing and direction of your eye darts will communicate more than almost any other thing in your scene" ([Animation Mentor](https://newsletters.animationmentor.com/newsletter/0607/feature_geek.html)).
- Start blinks at about 100 to 150 ms and tune by eye. I did not verify this against a primary study. The upper lid closes fast and opens slower, its edge following the eyeball's curve rather than wiping down flat.
- Saccades jump, then hold. Slowly drifting eyes look vacant.
- Eyes lead the head by a few frames, then the head, then the body.

## 6. Rigging for state machines

- **Layers run in parallel.** Each Rive layer plays one state at a time. When two layers touch the same property, the lower one wins ([Rive layers](https://rive.app/docs/editor/state-machine/layers)). Duolingo runs mouth states beside body states, with idle blinks, nods and brows on top ([Visemes](https://blog.duolingo.com/world-character-visemes)).
- **Blend states.** A 1D blend mixes timelines from one number. An additive blend uses several numbers and suits "poses and facial rigs" ([Rive states](https://rive.app/docs/editor/state-machine/states.md)).
- **Inputs.** Number, boolean and trigger inputs still work, but Rive marks them legacy and recommends Data Binding ([Rive Apple inputs](https://rive.app/docs/runtimes/apple/inputs.md)).
- **For SwiftUI, my suggestion.** Put pivots at real joints: neck base, wing root, ankle. Normalise every parameter to 0 to 1 like ARKit. Drive mouth-open from smoothed audio level. Add visemes only if that looks wrong.

## What this means for Milo

1. The silhouette reads at 36 pt as a solid fill, and reads as Milo, not "a bird".
2. One signature feature shows in the silhouette from every angle and at 36 pt. It never changes, like Freddie's wink.
3. Build him from circles on a flat, planted base. The beak is the only point.
4. His default pose is a three-quarter turn toward the screen centre, not face-on.
5. No two major parts share a size. Eyes stay large enough to carry lids at 36 pt.
6. Expression lives in lids, gaze and brows. Resting eyes sit about 70% open, because fully open reads as too happy.
7. Never smile at everything. The resting mouth is neutral. Smiles are earned, and he also has puzzled, concerned and sorry faces.
8. Idle motion beyond breathing stays under about 10% of the time. Nothing moves while the user types. Left alone, he dozes, like Neko.
9. He never interrupts and never acts out intent he doesn't have. The thinking pose plays only while work runs. Uncertainty is a puzzled look and a question, not a guess.
10. Eyes lead, and blinks have reasons: head turns and state changes. Random blinks only in idle.
11. Rig him as parallel layers: body, head, eyes, lids, brows, mouth, wings, feet, tail, accessory. Each takes 0 to 1 parameters. Mouth-open follows audio level.
12. Helpers use the same rig with fewer channels. At 36 pt that is body, signature feature, and eye dots with lids.
