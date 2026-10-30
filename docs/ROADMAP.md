# Milo roadmap

Written 2026-10-30. [TODO.md](../TODO.md) holds the small items. This file says where Milo is going and in what order. [VISION.md](VISION.md) has the bigger brainstorm: app connections, features, parallel helpers, sync and other devices.

## The product in one sentence

A small character on your Mac that you talk to, dictate with, and hand work to, and you can watch him do the work.

## Who it is for

People who have heard of ChatGPT but don't use AI day to day. The test is the user's mom: she should be able to install Milo, talk to her computer, and never feel she is "using a chatbot". That sets the design rules:

- **Talking is the main way in.** Typing is there for when talking is awkward. Nothing assumes the user knows what a prompt is.
- **No setup words.** No API keys, no config files, no "harness", no model names anywhere she can see. Settings are a few switches with plain labels.
- **She can see what Milo does, in her words.** "Opening Excel", "Typing the totals into column C", not `osascript -e ...`. The technical detail is one click away for people who want it.
- **She can see and fix what Milo remembers.** "Things Milo knows about you" as a readable list she can edit or delete from, backed by the same Markdown files.
- **Milo asks before anything she can't undo**, and stops the moment she says "stop" or presses `esc`.
- **Milo keeps track for her.** Appointments, plans, things to remember. He reminds her at the right moment without being asked again.

Three jobs, in the order people will discover them:

1. **Dictation.** The daily habit and the reason to install. It already beats Wispr Flow for the user, runs locally and costs nothing per word.
2. **Conversation.** The reason to keep him open. Voice in, voice out, memory, a character with a point of view.
3. **Doing things on the computer.** The reason to pay. "Fill column C with the totals", "rename these 40 files", "find the invoice from Hetzner and put it in the tax folder". Milo moves to the spot on screen where he is working, so you see what he does.

## What the limits are

**Computer use works, but pixels are the slow path.** Claude can drive a Mac from screenshots and clicks (the `computer_toolset_20260801` tool on Opus 5.5 and Sonnet 5.5). Every step is a screenshot round trip of a few seconds, every step costs tokens, and it still misclicks sometimes. So Milo should try routes in this order and fall back only when the faster one can't do the job:

1. Files and APIs directly. An `.xlsx` edited with openpyxl takes milliseconds and can't misclick.
2. AppleScript or JXA. Excel, Numbers, Finder, Mail, Safari and Notes are scriptable.
3. The Accessibility tree. Read the UI as named buttons and fields and press them by name. No screenshot needed.
4. Screenshots and clicks, for everything else.

Milo already runs Claude Code and Codex as his worker. The cheapest first version is an MCP server, `milo-mac`, that exposes routes 2 to 4 as tools to whichever CLI is configured. Raw Messages API computer use with an API key is the later path for the product.

**Selling it changes the login story.** Using your own Claude Code or Codex subscription is fine for personal use. Anthropic's Agent SDK docs say third-party products may not offer claude.ai login or subscription rate limits without approval, so a product needs either bring-your-own API key or a Milo backend that meters usage. Recheck the terms before launch.

**16 GB of RAM is the local ceiling.** Whisper turbo, OmniVoice and a 1 to 2B parameter chat model fit together. A 7B model next to them doesn't, comfortably. Hard thinking stays in the cloud.

**Distribution is real work.** A paid Apple developer account, Developer ID signing and notarization (also fixes permissions resetting on every rebuild), a bundled Python runtime, and a first-run download of about 3 GB of models with a progress screen.

**An agent clicking around your Mac needs brakes.** It asks before anything irreversible (send, delete, pay, overwrite), a global key stops it instantly, and the Milo window logs every action.

## Phase 1: now (three agents in parallel)

**A. Dictation that feels instant.**
- Hands-free: double-tap the dictate key to lock recording on, tap it again to stop and paste, `esc` to cancel. Holding still works as before. The talk key gets the same lock.
- Live transcription while you speak, with a setting:
  - `off`: transcribe on release (today's behaviour).
  - `preview`: words appear next to Milo as you speak. On release a final pass over the whole recording gets pasted. Same accuracy as today, and you can see it working.
  - `type`: text lands in the focused app at each pause while you are still talking. Feels fastest. Earlier segments don't get corrected later.
- A short mic pre-roll so the first syllable is never clipped.

**B. The Milo window.** One window with the conversation as text: what you said, what Milo answered (streaming in as he generates it), and an activity list of what the worker agent is doing (commands run, files edited, tools called). A text field continues the conversation by typing. The history survives a restart. Opened by clicking Milo or from the menu bar. Phase 2 shows computer use in this same activity list.

**C. A character worth remembering.**
- A character sheet ([CHARACTER.md](CHARACTER.md)): who Milo is, how he talks, what he never does, and what separates him from Clippy and Siri. The persona prompt follows it.
- Three visual directions drawn as an interactive concept page (`docs/design/character-concepts.html`). The user picks one before anything gets redrawn in Swift.
- Life that doesn't depend on the drawing: eyes that follow the cursor, idle behaviour (glancing around, stretching, yawning when it's late), squash and stretch between states, leaning in while listening, a reaction to being hovered.

## Phase 2: Milo uses the computer

1. `milo-mac` MCP server (Swift, runs inside the app since it already holds Accessibility permission): `list_apps`, `ax_tree(app)`, `ax_press(element)`, `ax_set_value`, `run_applescript`, `screenshot`, `click(x, y)`, `type(text)`. Attached to the worker CLI with `--mcp-config`.
2. Milo flies to the element he is about to act on and points at it. The overlay panel already floats over everything, so this is animation plus a coordinate from the tool call.
3. Confirmation gate in the app for irreversible actions, and a stop key.
4. Demo tasks used as tests: fill an Excel column from a formula description, file a PDF from Downloads, reply to the newest Mail message as a draft.
5. Routines. After Milo does a task, the user says "remember how to do this, call it the Monday report". Milo writes the steps as a plain recipe in `~/Milo/routines/monday-report.md`: what to open, what to fill in, what to check. "Do the Monday report" or a schedule ("every Monday at 9", through the existing zero-token heartbeat) runs it again. The agent follows the recipe rather than replaying recorded clicks, so a moved button doesn't break it, and it asks when something looks different from last time. The user can list routines, rename them and delete them by voice or in the Milo window.
6. Calendar. Read events through EventKit in the app (one permission prompt), "you have the dentist in 30 minutes" as a local heartbeat rule, and "put lunch with Anna on Friday at 1" as a write.
7. Conversation mode: open mic with end-of-turn detection and barge-in (talk over Milo to interrupt him), building on Phase 1's lock.
8. Answer small talk with a local model in under a second (already in TODO) and hand real tasks to the worker.

## Phase 3: a product

- Developer ID signing, notarization, a DMG and Sparkle updates.
- First-run onboarding: permissions one at a time with a short reason each, model download with progress, a 30 second dictation tutorial.
- A Milo account with a hosted backend that calls the models and meters usage. The target user will never have an API key or a Claude Code login, so this isn't optional for her. Bring-your-own key and the CLI logins stay as an option for technical users.
- Settings UI instead of hand-editing `config.toml`, and a "Things Milo knows about you" screen.
- Pricing to decide. One option: dictation free forever (it costs nothing to serve), a monthly subscription for conversation and the agent, with usage limits that the backend enforces.

## Later

Everything in TODO.md's "Later" list, plus: calendar awareness, a "what's this?" hotkey for the current selection or screenshot, a wake word, Windows (only if the Mac version sells).

## Open questions for the user

- Which of the three character directions?
- Personal tool first, or design every choice for strangers from now on?
- Is the agent's default "ask before acting" or "act, then tell me"?
