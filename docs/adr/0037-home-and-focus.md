# 37. The home and Focus from the talker

Date: 2026-11-01. Status: accepted. Builds on [ADR 29](0029-quick-actions-from-the-talker.md), [ADR 23](0023-stop-for-what-cant-be-undone.md), [ADR 27](0027-a-platform-boundary.md) and [ADR 35](0035-small-things-just-happen.md).

## Context

"Connect to home stuff", using "any home system that is connected, or the default". Lights, plugs, scenes and heating should just happen. Locks, garage doors and alarm systems should ask first. And "Do Not Disturb on" should be as quick as a timer.

Until now the only way was `<shortcut name="Lights off"/>`: it asks every time (a shortcut can do anything), has no Undo, and the model had to know the shortcut's exact name.

## Decision

**A `Home` port in core** (`core/ports.py`, `core/home.py`): `devices()` gives each device's id, name, room, kind (light, switch, scene, climate, fan, cover, garage, lock, alarm, other), state, level, what it can do and, for a scene, the devices it sets. `act(id, do, value)` does one of on, off, toggle, set, run, open, close, lock, unlock, arm, disarm. It is on `Connections.home`, so the fakes bring their own and the brain's quick actions and `<today>` reach it like the calendar.

**Adapters, picked by `[home] use`** (`HOMES` registry, `adapters/home/`):

- `home_assistant`: the REST API (`/api/states`, `/api/services/<domain>/<service>`, areas from one `/api/template`), with the URL in config and a long-lived token in `~/Milo/secrets/<key_ref>`, read through `read_secret` when first needed. A cover with device class garage or gate is a garage. Works on every OS.
- `apple_home`: a Mac app can't reach HomeKit without an entitlement Apple only gives to apps it reviews, so Home comes in through the user's own shortcuts, in a "Milo Home" folder (`shortcuts list --folders`, then `--folder-name`; a missing folder lists as empty, so the folders are asked first). Names are parsed: "Living room lights on" and "… off" are one device, "Movie night" a scene, „Haustür abschließen“ a lock. A name that says lock, door, garage, gate or alarm (or the German words) is a lock, a garage or an alarm. Without the folder, the shortcuts whose names are about the home count, but ask like any shortcut (`Device.known` false): a name can say "lights" and do anything, and only the folder says the user meant them for this.
- `auto`, the default: Home Assistant when `[home.home_assistant]` has a url, else Apple Home where the `shortcuts` command exists, else none. compose hands it every `[home.*]` table. A home the connections bring (the fake one) stays.
- `none`.

**One tag.** `<home device="Kitchen lights" do="off"/>`, `<home device="Heizung" do="set" value="21"/>`, `<home scene="Movie night"/>`. Names are matched forgivingly (`core.home.find`): an exact name wins; else every device whose name, room and kind hold all the words said, with synonyms in both languages ("lamp" and „Licht“ are light, „Küche“ is kitchen) and German compounds by their parts („Küchenlicht“). "The kitchen lights", „alle Lichter“ mean all that match, of one kind; one light said where several match gets "Which one: …?". On blinds and garage doors on and off are open and close.

**The names where the model sees them.** `<today>` gets a "Home" part: rooms with their devices, then the scenes, at most 40 names, no states. States change all the time, and every change would send the whole block again. The devices are read at most every 30 minutes and the block waits 0.25 s for them at most; a slow home goes into the next block.

**Asking.** Lights, plugs, scenes, heating, fans and blinds are `change`, and `light`: in auto mode at the Mac outside text doesn't make them ask (ADR 35); in the stricter modes it does. Locks, garage doors and alarms are a new kind, `lock`, at `ask_first`: they ask every time, in every mode, and Undo of one asks again. So does a scene whose devices include one. What Milo can't see into (a Home Assistant script, a scene that names no devices, a shortcut outside the folder) is `shortcut` and asks every time. A scene in the user's own "Milo Home" folder can't be seen into either, but the user put it there and asked for scenes to just happen; its name still makes it ask when it says lock, door, garage or alarm. `[approvals.levels] lock` can change that. The generic `<shortcut>` still asks every time.

**Undo, back to how it was.** Before acting, each device's state is kept and Undo sets it back: off again, on at its old brightness after a dim, the old temperature or heating mode, the blind's old position, locked again. A scene's Undo puts back the devices it sets, as they were. Where the home can't say how a device was (shortcuts), Undo does the opposite (`… off` after `… on`); a shortcut scene has none.

**Focus.** `<focus do="on|off" name?/>` on a `Focus` port. macOS has no public API for it, only Shortcuts' "Set Focus" action. For Do Not Disturb Milo makes the two shortcuts himself when they are missing: a one-action workflow (`is.workflow.actions.dnd.set` with the Do Not Disturb mode) written as a property list, signed with `shortcuts sign --mode anyone` (Apple's signing service, about 8 s) into the state folder, and opened, so Shortcuts shows "Add Shortcut". The user clicks Add on each, once, and asks again. Another Focus has an id Milo can't know (the user's own are made-up ids), so for those Milo says how to make "Work Focus on" and "… off", and finds them by name. The name has to say Focus: a Focus never asks, and a shortcut called just "Work on" could do anything (changed after review). Focus never asks; Undo switches it back (Milo can't read whether it was on: the Focus database needs Full Disk Access).

**Lines.** `core/words/home.py`, English and German: "Kitchen lights: off.", „Heizung: 21 Grad.“, "Scene on: Movie night.", "Do Not Disturb is on." "{title}: off" rather than "is off", since the title can be one lamp or all of a room's. The card is `action_done` kind `home` (app: the home's name) or `focus`; the app shows them as plain cards with a check until it knows the kinds.

## Consequences

- "Turn off the kitchen lights" is one tag and one HTTP call, with no question and an Undo.
- Not tried on a real Home Assistant or a real Apple Home. The REST calls follow Home Assistant's documented API; the tests stub HTTP. The `shortcuts list --folders`/`--folder-name` behaviour and `shortcuts sign` were checked on a Mac; importing the signed Do Not Disturb shortcuts and running them was not, so whether Shortcuts reads the made workflow exactly as meant is not verified.
- The user does something once: a token file for Home Assistant, or a "Milo Home" folder of shortcuts, and two clicks for Do Not Disturb.
- Helpers (the worker) don't get the home: it is the talker's, like the music.
- An alarm panel that wants a code can't be armed or disarmed.
- Device names in `<today>` are the user's own and not marked as outside text, but they are made inert like titles.
