# 40. A small decision model reads what the user asked for

Date: 2026-11-01. Status: accepted. Changes how [ADR 22](0022-one-question-per-piece-of-work.md), [ADR 28](0028-open-at-once-and-answer-in-the-users-language.md), [ADR 33](0033-milo-writes-where-you-are.md) and [ADR 35](0035-small-things-just-happen.md) tell that the user's own words asked for something. Follows [ADR 27](0027-a-platform-boundary.md) for where it lives.

## Context

After Milo has read outside text (a page on the screen, a mail, a task result), his tags only act without a question when the user's own words asked for it. A link opens, a helper works without asking before each change, a program installs, a fact is kept and a written text is pasted. Until now lists of words decided this: English and German verbs (`asks_for_work`, `_INSTALL`, `_REMEMBER`, `writing.asks_to_write`), "can you" and "kannst du", question words and negations.

The lists kept missing what people say. On 2026-11-01 the user looked at a YouTube page and said "Wie wäre es, wenn du jetzt einfach mal den Titel und alle Empfehlungen in eine Excel-Tabelle packst". Neither "packst" nor "wie wäre es, wenn du" was in a list, so the task ran careful and asked "Darf ich direkt in Google Chrome arbeiten?" again, after the user had pressed Allow always. Each fix added more words. The user: "Please don't hardcode these values … Shouldn't the LM figure this out? What if I change to a different language?"

The talker can't be the one to decide: it reads the outside text that might be steering it. What decides has to see only the user's words, and answer quickly.

## Decision

**A decision model on the computer.** It is vLLM Semantic Router's d3-lite (0.85B, Qwen3.5 backbone, Apache-2.0), on the Mac's GPU through PyTorch. A decision model scores every answer to a typed question in one forward pass and generates no text: a yes-or-no comes back as the probability of yes, a choice as a probability per option. The candidates were:

- **Decision 3.0** (d3-edge to d3-ultra) and **Vela 3.0**, which is d3 with routing adapters. Our own questions run Vela with its adapters off, so they are plain d3-lite.
- **GLiClass** multilingual.
- **vela3-fast**, which is English only.

d3-lite reads German at 79% on MASSIVE intents. It is 1.7 GB, takes about a third of a second per question on the GPU (seconds on a CPU), and its runtime code comes with the model at a pinned commit (`D3Options.revision`).

**Where it lives.** The port is `core/decide.py`: `Decider.decide(text, {name: YesNo | Choice})`. The adapter is `adapters/decide/d3.py`, chosen with `[decide] use` ("d3" on a Mac, "none" elsewhere for now). `services/decisions.py` runs it on its own thread and has two jobs:

- **`Decisions.intent(request)`** reads the user's own words in a turn and returns `Intent(work, install, remember, write)`. The questions are in `ASKS`. "Work" is the mean of a choice (action, look, question, undo, chat) and a yes-or-no: each alone missed requests the other found, and the choice keeps "undo that" and "look at my screen" from counting as work. Thresholds are in `ASKED`. It never raises. With no model, a failure or no answer within `[decide] wait_s` (8 s), nothing counts as asked, and Milo asks first. A reading takes about 2 s alone and 3.1–3.2 s inside a turn, next to speech and the screen reading, so the first limit of 3 s missed every one. The talk key wakes the model after a minute unused (`Decisions.wake`): after a night idle macOS had paged it out.
- **`Decisions.classify(items, classes, question)`** is the helpers' `classify` tool (`connect/milo_tools.py`, op `classify` on tools.sock). It sorts up to 200 texts into 2 to 50 classes the helper names, with each class's probability. It only reads, so it asks nobody. Its description warns that a text can sway its own class.

**In a turn.** LiveTalk starts the reading when the words arrive (`_take_request`), next to recall and the model's first words.

- A reply never waits for it before speaking: 4–5 questions take 1.5–2 s on the GPU. A tag that acts while the reply streams uses the reading if it is already there, and is otherwise treated as if nothing was asked (`_rule_now`).
- At the end of the reply LiveTalk awaits the reading and builds the final `TagPolicy`. Tasks, installs and facts start from that policy. An `<open>` held only because the reading wasn't there yet opens then without a question (`_release`).
- `Writer` awaits the reading itself before it decides whether a `<write>` after outside text goes in.

`TagPolicy` takes the `Intent` (`policy(intent=)`) and gains `own_write`. The word lists are gone.

**What stays.** Two checks that aren't about meaning are unchanged:

- A fact must share a word stem with the request (`_from_request`), so a mail can't add a fact of its own next to the one asked for.
- An install still has to name the exact package (`core/packages.named_by`).

**Measured** on 113 sentences: the tests' table, the old lists' cases and the user's real ones, in German, English, French and Spanish (`tests/eval/test_decisions.py`, run with `MILO_MODEL_EVAL=1`). 109 are read as the table says. The 4 misses fail on the safe side or are caught later:

- "what can you open?" and "what did I ask you to remember?" count as work.
- "install what the page mentions" and "Mach mir bitte YouTube in Chrome auf" read as an install; `named_by` then wants a package name the user said.

On the real Milo, after he read the YouTube page, "Wie wäre es, wenn du mal das Hearthstone-Video aufmachst?" was read as work in 1.9 s and the helper clicked it without asking.

The questions were tuned on these sentences, so new phrasings belong in the eval.

## Consequences

- Requests in any language the model reads let Milo go on after outside text. The questions and thresholds can be changed without editing word lists.
- About 1.7 GB more memory while the brain runs, and a 1.7 GB download on first start (`[decide] use = "none"` turns it off). torch and transformers come with the `omnivoice` extra the app already installs.
- With the model off or too slow, after outside text Milo asks more, never less.
- An `<open>` of a link that the reading allows can open at the end of the reply instead of mid-sentence, when the tag came before the reading.
- Tests use `tests/fakes.FakeDecider` with the `READINGS` table, and the eval checks that the real model agrees with that table.
- Linux and Windows get "none" until they have a GPU path, so they ask more after outside text than with the old lists. `[decide] use = "d3"` works there with CUDA.
