# 34. One place for each thing

Date: 2026-10-31. Status: accepted. Builds on [ADR 27](0027-a-platform-boundary.md) (the platform boundary), [ADR 28](0028-open-at-once-and-answer-in-the-users-language.md) (the user's language), [ADR 29](0029-quick-actions-from-the-talker.md) (quick actions and `<today>`) and [ADR 31](0031-talk-as-naturally-as-dictation.md) (the cached system prompt). Changes ADR 29's `AppOps` and where Milo's own reminders reach the talker.

## Context

Milo grew fast, feature by feature, and some things ended up in several places at once:

- What Milo says lived in eight modules, each with its own English and sometimes German table (`quick_words`, `approvals`, `hands`, `opener`, `updates`, `writing`, `wording`, `live_talk`). Undo and routines had no German at all. A new line meant finding the right table first.
- About ten functions read a time from a file, the app or the model, each a little differently. Some kept a time zone and some didn't, so comparing two of them could raise.
- `live_talk.py` was 900 lines: the prompt text, four slightly different rules for when a tag waits for a yes, what a finished reply's tags do and their questions, and the turn itself.
- Quick actions and `<today>` reached Calendar and Reminders by op name through `AppOps`, beside the `Calendar` and `Reminders` ports the worker uses. The morning brief and meeting notes called the app by op name a third and fourth way, and the brief fetched the day again though `<today>` had just read it.
- Milo's open reminders sat in the cached system prompt, so setting one changed the prompt.
- `[ui] character` picked between characters after there was only one, the wren.

## Decision

Each of these has one home now, and new work goes there.

**What Milo says: `core/words`.** One catalogue, `CATALOGUE[key][lang]`, built from one module per area (`acts`, `talk`, `hands`, `approvals`, `opener`, `updates`, `writing`, `connect`, `undo`, `routines`). `say(key, lang, **values)` fills a template and falls back to English for a language or a key a table lacks. `core/words/dates.py` (formerly `core/dates.py`) has the day and clock words. A test checks that every key has English and that no other language uses a placeholder English lacks. Every English line moved byte for byte. Undo and routines now speak German too. Prompts for the models and helpers' task text stay English.

**Reading a time: `core/times.py`.** `local(value)` reads an ISO time: an aware one becomes local time and then loses its zone, a naive one is taken as local. `parse_local` is the same but gives None for something unreadable. `minute`, `parse_minute` and `iso_minutes` write and read the minutes `reminders.md` and the app use. Times inside the brain are naive local times. The app sends naive local times, so only a model's `…Z` reads differently than before: as the local time it means.

**The talker in four files.**

- `talk_prompt.py`: the rules text and `system_prompt(PromptParts)`. With quick actions on, the `<task>` rule no longer sends the calendar, reminders, mail drafts or notes to a helper: the act tags do them.
- `tag_policy.py`: one `TagPolicy` per reply, worked out when it starts, from what the conversation has read (`tainted`, `saw_screen`), whether the message itself carries outside text (`now`), and auto mode at the Mac (`at_mac`, `own_work`). `outside` holds every tag that takes effect at once. `ask_undoable` is the auto-mode exception for an address and an act the user asked for. `ask_tasks`, `ask_routines`, `careful` and `user_asked` are for helpers. `asks_for_work` lives here.
- `reply_effects.py`: `ReplyEffects` applies a finished reply's tags (facts, reminders, tasks, steers, stops, routine runs, undos) and asks first where the policy says. The question builders (`task_question`, `open_question`, …) live here too. `task_question` drops "on the user's <computer>" with `Platform.computer`, so the core names no Mac there.
- `live_talk.py`: the turn. Streaming, interrupting, holding, the conversation, looking, and starting `<open>`, acts and `<write>` while the reply streams.

**The brain's calendar: the ports.** compose builds the brain's own `Connections` once (`_brain_connections`): the worker's adapters minus the switched-off ones. `services/connections.in_brain` swaps the ones the app holds for AppBridge-backed ones. `core/app_connections.py` (`AppCalendar`, `AppReminders`, `AppPlayer`) turns the ports' calls into the app's `app_request` ops over any call: blocking through the tool socket for the worker's mac adapter, awaiting AppBridge in the brain. `reach(method, …)` awaits an app-backed method or runs a blocking one on a thread. Quick actions, `Today`, the brief (through `Today.current`) and meeting notes all use it. `AppOps` is gone.

**Milo's reminders: `<today>`.** The open reminders from `reminders.md` go in the `<today>` block under "Milo's reminders:". The system prompt no longer lists them. Without quick actions LiveTalk keeps a `Today` that carries only these. `reminders.md` stays Milo's own store.

**One Milo.** `[ui] character` and the wire's `character` field are gone. An older config or brain that still has them loads, and the value is ignored.

## Where new work goes

- A line Milo says: a key in the `core/words` module of its area, English first, German where you can. Never an f-string in a service.
- A date or a time in text: `core/words/dates.py`. A time read from anywhere: `core/times.py`.
- A new tag that takes effect at once: let it follow `TagPolicy.outside` (or `ask_undoable`, if it can be closed or undone); add a property to `TagPolicy`, with a test in `test_tag_policy.py`, if it needs its own rule.
- Something a finished reply's tag does: `ReplyEffects`. Prompt text: `talk_prompt.py`.
- Calendar, Reminders or the player from the brain: `reach` on `p.connections`, never an op name.
- Anything that changes per turn: a block in the user message (`<today>`, `<memory>`, `<helpers>`), never the system prompt.

## Consequences

Behaviour changes, each on purpose:

- **Unified tag rules.** After a look in an earlier turn of the same conversation, and nothing else from outside, an act tag, `<remember>` and `<reminder>` now ask first, like `<open>` and `<write>` already did. ADR 29 said acts did. In auto mode at the Mac an act the user asked for still just happens (ADR 28). A careful helper is never `user_asked`. Before, a task after a look could be both, and auto mode then skipped its careful questions (ADR 23's update).
- **Reminders** reach the talker in `<today>`, in the next message, rather than in the next conversation's system prompt. Setting one no longer throws away a warmed conversation. Reminder text is made inert, cut at 200 characters.
- **The `<task>` rule** with quick actions on no longer names the calendar, reminders, mail or notes as helper work.
- **The brief** reads the same two-day window `<today>` reads. With the fake connections, the brief and meeting notes read the fake world, like quick actions. A failure to read the day leaves out both its calendar and its Apple to-dos.
- **German** for Undo and routines.
- **Dead code** out: the old single-file transcript store, `sheets.app_name`, and a few unused functions. The portability guard is down to 54 exceptions in 29 files.

What it costs: `core/words` is one more place to look when a line reads wrong, but the only one. `TagPolicy` is computed when the reply starts, so changing `[approvals] ask` mid-reply applies from the next reply.
