# 36. Music by name, the volume and the screen's brightness

Date: 2026-11-01. Status: accepted. Builds on [ADR 29](0029-quick-actions-from-the-talker.md) and [ADR 35](0035-small-things-just-happen.md).

## Context

"Play Taylor Swift", "turn it down", "make the screen brighter" are what people say to Siri most. Milo could press play, pause, next and previous (`<music>`, through the system's now-playing controls) and nothing else. Anything by name went to a helper, about 15 s and tens of thousands of tokens for one song, or nowhere.

## Decision

**Three tags, done by the brain at once, like every quick action.** `<music do="play" query="Taylor Swift" kind="artist"/>` (kind: artist, song, album, playlist, genre or any; `app` only when the user names one), `<volume level="40"/>` or `do="up|down|mute|unmute"`, `<brightness do="up|down" steps="2"/>`. Each says one short templated line ("Playing Taylor Swift.", "Volume at 40.", "Brighter.", English and German), shows a card (`music`, `sound`, `brightness`) and has an Undo.

**None of them asks.** Their plans have no action kind (`_Plan` approval None), like a timer: nothing leaves the computer, nothing is lost, and the card's Undo puts it back. Outside text in the conversation doesn't change that. A switch in `[connections]` (`music`, `volume`, `brightness`) turns each off.

**Three new ports, platform specifics in the adapters.** `MusicApps` (which, scripts, play, running, playing, resume, pause), `Volume` (get, set) and `Brightness` (change) in `core/ports.py`, on `Connections`.

- *Music* on the Mac goes through its AppleScript dictionary (`adapters/connect/mac_sound.py`). A playlist plays by its name. Anything else fills a playlist called "Milo" with the matching library tracks (up to 200), shuffled unless it is an album, and plays it: one playlist Milo owns and refills, rather than a new one each time or touching the user's. What isn't in the library can't be played by a script (the Apple Music catalogue has no AppleScript), so Music's search opens and Milo says "“Bad Bunny” isn't in your library, so the search is open in Music."
- *Spotify* plays a Spotify address (`spotify:album:…`, `open.spotify.com/…`). A search can only be played through Spotify's web API, which needs an app registration and the user's login: out of scope. So "play Taylor Swift on Spotify" opens Spotify's search and says honestly that the user picks there.
- *Which app.* The one the user names; else `[connections] music_app`; else the one running (Spotify only when it runs alone), else Music.
- *The volume* is `set volume output volume` and `output muted` (Standard Additions, no Automation permission). A level or "louder" also unmutes; "quieter" leaves muting alone. Steps are 10 of 100.
- *The brightness* has no public API for every screen; the brightness keys work wherever the keyboard's do. The app presses them (`media.brightness_up`, `media.brightness_down` {steps}, NX_KEYTYPE_BRIGHTNESS_UP 2 and DOWN 3, posted like the media keys) through a `BrightnessKeys` port. One press is one of 16 steps; "brighter" is 2 unless the model says more.

**Undo.** A play records what played before in the same app (read by the same script, so no second round trip): Undo plays that track again from where it was, or pauses when nothing played or it can't be found (a stream not in the library). The volume goes back to its level and mute. The brightness presses the other key as often.

**What plays, in `<today>`.** "What's this song?" should need no tool. `<today>`'s music line now says "Music: playing “Shake It Off” by Taylor Swift in Music." A script takes about half a second (0.6 to 1.3 s measured under load), longer than a turn waits for the block, so the read starts in the background when the user starts talking (`Today.soon`), at most every 5 s, and the block takes it once it is there. It reads only apps that run (`pgrep`, which starts nothing) and that Milo may script already (`AccessGate.allowed_now`, which asks nobody): reading what plays must never bring up the system's Automation question out of nowhere. Track titles are made inert and don't make the conversation count as outside text: most turns while music plays would otherwise ask (ADR 35's complaint).

## Consequences

- "Play Taylor Swift" costs one short reply and one script: about the talker's 1 to 2 s, plus the script (0.5 to 2 s for filling the playlist one track at a time).
- Only the library plays by name in Music; the catalogue opens a search. Spotify by name never plays by itself.
- An album added to the "Milo" playlist is in library order, which is usually but not always track order.
- Brightness keys only reach screens that take them (built-in, Apple displays); others don't change, and the line still says "Brighter." At the top or the bottom of the range a press does nothing, and its Undo then moves the other way.
- A song title in `<today>` is someone else's text, read as data, not taint. A malicious title can't open a tag (inert) and acts it suggested would still be the user's own small, undoable kind.
- Not run on a real Mac: the Music play, resume and pause scripts (compiled with `osacompile` only, to play nothing during development), every Spotify script (Spotify isn't installed where this was written), the `music://` search address, and the brightness keys. The volume read ran for real; setting it did not. Tests use a fake script runner and the fake world.
