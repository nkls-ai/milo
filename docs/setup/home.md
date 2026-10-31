# Your home and Focus

Milo switches lights, plugs, scenes, heating, fans and blinds when you ask ("turn off the kitchen lights", „Heizung auf 21 Grad“, "movie night"). Each one just happens and shows a card with Undo. Locks, garage doors and the alarm ask you first, every time.

He uses one home system, set in `~/Milo/config.toml` under `[home]`. With `use = "auto"` (the default) that is Home Assistant when it has an address, else Apple Home through your shortcuts.

## Home Assistant

1. In Home Assistant, open your profile (bottom left), then **Security**, and under **Long-lived access tokens** click **Create token**. Name it "Milo" and copy it.
2. Put the token alone in a file: `~/Milo/secrets/home_assistant.token`. Nothing else goes in the file.
3. In `~/Milo/config.toml`:

   ```toml
   [home.home_assistant]
   url = "http://homeassistant.local:8123"
   key_ref = "home_assistant.token"
   ```

4. Menu bar item › Restart brain.

Milo sees lights, switches, scenes, scripts (they ask first, like a shortcut: Milo can't see what they do; so does a scene that names no devices), heating (climate), fans, covers (blinds, and garage doors or gates by their device class), locks and alarm panels, and the rooms (areas) they are in. The names he uses are the names Home Assistant shows. An alarm panel that wants a code can't be armed or disarmed by Milo.

## Apple Home, through Shortcuts

A Mac app can't reach Apple Home directly: Apple keeps that for apps it reviews. Shortcuts can, so Milo runs your shortcuts.

1. Open **Shortcuts** and make a folder called **Milo Home** (File › New Folder).
2. In it, make one shortcut per thing you want, with the **Control Home** action (in Shortcuts' Home category) set to the scene or device:
   - A scene: name it like the scene, e.g. "Movie night" or "Gute Nacht".
   - A device that goes on and off: two shortcuts, "Living room lights on" and "Living room lights off" (or „Wohnzimmer Licht an“ and „… aus“).
   - Blinds or a garage door: "Blinds open" and "Blinds close" (or „Rollo auf“ / „Rollo zu“).
   - A lock: "Lock front door" and "Unlock front door" (or „Haustür abschließen“ / „Haustür aufschließen“).
   - A level: "Heizung set" or "Desk lamp dim", whose shortcut takes the number Milo passes as its input (use **Shortcut Input** in the action).
3. That's it: Milo reads the folder when you ask. No restart needed.

A shortcut whose name says lock, door, garage, gate or alarm (or Schloss, Tür, Tor, Alarm) always asks first, whatever it does. Without the "Milo Home" folder, Milo looks at all your shortcuts and takes the ones whose names are about the home, but each of those asks first like any shortcut: a name can say "lights" and do anything. The folder is how you tell Milo they are what they say.

Shortcuts can't tell Milo whether a light is on, so Undo runs the opposite shortcut ("… off" after "… on"). A scene has no Undo there.

## Focus and Do Not Disturb

"Do Not Disturb on", „Nicht stören aus“, "turn on my Work focus": Milo switches it without asking, and Undo switches it back.

macOS has no way for an app to switch a Focus except through Shortcuts' **Set Focus** action.

- **Do Not Disturb:** the first time, Milo makes two shortcuts himself ("Milo Do Not Disturb On" and "… Off") and opens them. Click **Add Shortcut** on each, then ask again.
- **Another Focus** (Work, Sleep, your own): make two shortcuts with the Set Focus action, named "Work Focus on" and "Work Focus off" (or „Fokus Arbeit an“ / „Fokus Arbeit aus“). Milo finds them by the word Focus, the Focus's name and "on" or "off", nothing else: a Focus never asks, so a shortcut called just "Work on" isn't taken.

## Switches

- `[home] use = "none"`: no home at all.
- `[approvals.levels] lock = "change"`: locks, garage doors and the alarm stop asking. Think twice.
- `[connections] enabled = false` also switches the home and Focus off.
