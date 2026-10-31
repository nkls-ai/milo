# 24. Milo leaves the screen when nothing goes on

Date: 2026-10-31. Status: accepted.

## Context

The user: "Milo should, if you didn't talk to him for like a minute or so, hide from the screen. Or you can toggle how long you want him to stay on the screen, default like a minute. If you don't talk to him and then if you of course press the button to dictate or talk to him, he comes up again and have like a nice animation to do that."

A hidden Milo must never cost a click. The user once couldn't click Milo's Yes and Allow, and that was a top-priority bug. The old "Hide Milo" ordered the panel out until "Show Milo", questions included.

## Decision

- **One rule for staying.** `Presence.needs(model)` is true for anything the user may need from him: any state but idle, a bubble, a question, `canStop`, the voice capsule, an active helper, hands work, looking, a meeting that records or is being written up, a working window, a fly target or a flight. The user dragging him counts too. He never leaves while it is true, and comes back the moment it turns true. "Hide Milo" follows the same rule: the item is disabled while he is needed, and he comes back like after a wait. The old way, ordering the panel out until "Show Milo", is gone.
- **Following the model, not hooking it.** Presence watches `objectWillChange` and looks again a moment later. Every way the model changes is covered, including the screen and meeting controllers' fields. The keys and the menu bar call `summon()` directly: a quick tap of the key brings him back too, which a look a moment later could miss.
- **The motion lives inside the panel.** `Presence.Pose` is an offset, an opacity and a flight heading for the wren, as a pure function of time. The panel stays where it is, so it never fights `FlightDriver`, and the move can be rendered frame by frame in tests. The panel is ordered out only once he is gone, and in again before the first frame of his return. The way back is the way off run backwards, so turning round halfway is seamless.
- **The setting.** `[ui] hide_after_s` (seconds, 0 = never, default 60) in Settings as four plain choices. The app reads it from each `settings` report, so it applies at once and the brain only stores it. A time set by hand shows in words as an extra choice.
- **Not offline.** A brain that is gone doesn't hold him on screen: one that never comes back would keep him up for good.

## Consequences

- Clicking the menu bar icon always brings him back, so the menu's item now only reads "Hide Milo".
- He leaves past the panel's edge, which is the screen's edge only while he sits in his corner. Dragged elsewhere, he fades out before much of him is cut.
- Each change to the model costs one extra main-queue turn, and only one look is ever pending.
