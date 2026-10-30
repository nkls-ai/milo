# 16. Routines: recipes in words, run by a helper

Date: 2026-10-30. Status: accepted. Builds on [ADR 3](0003-zero-token-heartbeat.md), [ADR 10](0010-untrusted-results-and-a-private-log.md) and [ADR 11](0011-helpers-and-the-orchestrator.md).

## Context

The user wants to say "remember how to do this, call it the Monday report" after Milo did something, and later "do the Monday report", "the Monday report for October", or have it run every Monday at 9. The research in [docs/research/routines.md](../research/routines.md) looked at how others keep and replay agent work. Recorders that replay clicks (OpenAdapt, workflow-use, Shortcuts' own actions) break when a window moves. Agents that keep skills as Markdown (Claude skills, OS-Copilot, OpenClaw) survive that, because the next run re-plans from words. workflow-use and Skyvern are AGPL, so no code was taken from them, only ideas.

## Decision

- **A routine is a Markdown recipe** in `~/Milo/routines/<slug>.md`: front matter with `name`, `description`, `inputs` (name, the question, a default in words like "last month"), `schedule`, `apps`, `paused`, `last_run` and `version`, then a body with Goal, Steps (each with a `Check:` line), and Ask first. The front matter is a small subset of YAML read by `core/routines.py` with the standard library. The user can open and edit the file. `last_run` and `paused` are changed in place, so their own edits stay.
- **Written by a helper, kept after a look.** `<routine do="create">` starts a careful helper (`Helper.careful`) that turns the last helper's task, steps and result into a draft in `state/routine-drafts/`. Concrete values that change become inputs, steps say what to do rather than where to click, and steps that send, delete, move or overwrite are marked "(asks first)". The brain parses and normalizes the draft and sends it to the window, where the user saves it, changes it, or throws it away. Save keeps the text the window showed, not whatever the file says by then.
- **Run by a helper.** `<routine do="run">` starts an ordinary helper with the recipe, the inputs (given, or defaults) and rules: verify each Check, stop and ask when the world looks different instead of improvising, never do a destructive step without asking. The run gets its own transcript entry. At the end the brain records `last_run` and a line in `state/routine-runs.jsonl`. `Routines.on_episode` is the hook for the memory's episode log.
- **Approved by fingerprint.** Saving records a hash of the body, inputs and apps in `state/routines.json`. A recipe whose fingerprint changed since (a hand edit, or a worker writing into the folder) asks before it runs, once. A schedule that shows up in a file without being set through Milo asks before its first run. A routine run is a task, so in a tainted conversation it asks like any other tag. The name in the run prompt is reduced to plain characters, since renaming doesn't ask.
- **Schedules on the heartbeat.** `HeartbeatRunner.on_tick` calls `Routines.tick(now)`: no model call, a comparison of each schedule's last due time with what was handled. Plain-word schedules ("every Monday at 9", "every weekday at 8:30", "on the 1st of every month at 9") are parsed by `parse_schedule`. Runs the Mac slept through are coalesced into one, like launchd. It runs at wake within `[routines] grace_hours` (4), and is reported instead after that. `[routines] max_runs_per_day` (6) caps scheduled runs, and a run over the cap is reported.
- **Managed by voice and in the window.** Tags for save, change, schedule, rename, pause, resume and delete. The window's Routines section lists each routine with its schedule, next and last run, Run now, pause and delete (`routines`, `routine`, `routine_draft_answer` in `protocol/messages.json`). Delete moves the file to `routines/deleted/`.

## Consequences

- A routine survives moved buttons and new app versions, at the cost of a model run each time. A replay would cost nothing but break.
- The recipe is only as good as the helper's steps. Steps come from the transcript, which holds kind words and commands, not screen contents.
- Each run is a fresh plan, so two runs may take different routes to the same result. The Checks are what keeps them honest.
- Pattern detection (offering a routine after the same kind of task three times) is not built yet.
