# 38. Weather in the day at hand, and alarms that ring until you stop them

Date: 2026-10-31. Status: accepted. Builds on [ADR 29](0029-quick-actions-from-the-talker.md) (quick actions and `<today>`), [ADR 27](0027-a-platform-boundary.md) (the platform boundary) and [ADR 34](0034-one-place-for-each-thing.md) (where things go).

## Context

Two everyday questions had no fast answer. "Do I need an umbrella tomorrow?" went to a helper, which searched the web for 15 to 30 s. "Wake me at 7" could only become a `<reminder>`: one spoken line on the heartbeat's 30 s tick, said once and easy to sleep through, and a timer that doesn't survive a restart.

## Decision

**The weather rides in `<today>`.** A `Weather` port (`core/ports.py`) returns a `Forecast` (`core/weather.py`): one `DayWeather` per day with the WMO weather code, the low and the high, the chance of rain for each hour, how much falls, and the wind and gusts. The first adapter is Open-Meteo (`adapters/weather/open_meteo.py`, `[weather] use = "open_meteo"`, registered in `WEATHER`). It is free, needs no key, and works from the standard library's urllib. Its geocoding API turns the place's name into a position once per run, then one forecast request gets the week (`timezone=auto`, the units from config).

`WeatherReport` (`services/weather.py`) reads it on a thread, at most every 45 minutes. A failed read is logged and tried again after 10 minutes, and a forecast older than 6 hours is dropped. `Today.soon` starts the read when the user starts talking, and `Today.note` waits for it within the block's 0.3 s, so the first question of the day usually has it. `core/weather.lines` makes the lines:

```
Weather in Berlin (°C, km/h):
- Now: 7°C, partly cloudy.
- Today: 5–11°C, overcast, rain chance 5%.
- Tomorrow, Fri 30 Oct: 6–9°C, rain, rain chance 80%, mostly 14–18h, 4.2 mm in all, windy, gusts up to 62 km/h.
- Sat 31 Oct: 2–12°C, mostly clear.
```

Today's chance of rain counts from the current hour on: after a rainy morning the evening's umbrella question gets the evening's chance. The block is about 100 tokens. It is numbers from a service, not text a person wrote, so it doesn't make the reply or the conversation "outside" (`Today.render` keeps its flag). The talker's rules (`quick_actions.RULES`) say to answer weather questions from it, and to start a task for another place or when it isn't there.

**The place needs no location permission.** `[weather] place` names it ("Berlin", "Portland, Oregon", or "52.52,13.41"). Empty, it is the city of the system's time zone (`Europe/Berlin` → Berlin, read by `adapters/timezone.py` from TZ or `/etc/localtime`). A zone that names no city (UTC) leaves the weather out and logs why. The config comment says the place's name goes to Open-Meteo.

**Alarms are Milo's own, like timers, but kept and loud.** The talker writes `<alarm at="2026-11-01T07:00"/>`, with text inside only when the user said what for. `<alarm do="cancel" id="a1"/>` (or a title, or the only one), `<alarm do="stop"/>` for "okay, I'm up" and `<alarm do="snooze" minutes="5"/>` for "five more minutes". `QuickActions` plans them like a timer: Milo's own business, never asked (`_Plan(None, …)`). Setting, cancelling and snoozing show an `alarm` card with Undo. Stopping has no card. A time that passed less than a day ago means the next one, because at 11 pm the model writes today's date for "wake me at 7". A bare "07:00" also means the next 7:00. More than a week ahead is refused: that is a reminder's job.

`Alarms` (`services/alarms.py`) keeps them in `state/alarms.json` (a `StateFile`), so they survive a restart of the brain. `Alarms.run`, one of the brain's loops in `server.py`, checks the wall clock (`Clock.now`), at least every 30 s and exactly when one is due. A timer on the event loop wouldn't do: the loop's monotonic clock stops while the computer sleeps, so an hour's timer set before sleep would ring an hour of awake time later.

**Ringing** is a chime made in code (two notes, three times, about 2.4 s) played through the speaker's own utterance (`Utterance.interject`), then one line: "It's time: your alarm at 7 am." It cuts off whatever Milo was saying and comes again every 12 s, for at most 4 minutes. It waits only while the user speaks into the microphone. A key press, a typed message and the Stop button end it at once (`Brain._hush` on `listen_start`, `text_input` and `stop_all`). What the user says then reaches the talker, and `<today>` says "Alarm that just rang: 07:00, stopped." for 30 minutes, so "five more minutes" can snooze it and "I'm up" gets "Alarm off." The app's esc key isn't sent to the brain when Milo isn't listening, so esc alone doesn't stop it. That would need a new command from the app.

**Nothing can ring while the computer sleeps.** Waking it needs root (`pmset schedule wake`), which Milo doesn't have and shouldn't ask for. So the first alarm set more than an hour ahead adds one line: "I can only ring while the Mac is awake." It is said once ever (`told_sleep` in the state file). An alarm found more than 10 minutes after its time doesn't ring late. Milo says "I missed your alarm at 7 am: the Mac was asleep." and drops it.

**Words** are in `core/words/acts.py` (English and German): `acts.alarm*`, `acts.card_alarm`, `acts.card_snoozed`, `acts.which_alarm`, `acts.why_alarm_*`. The app's card has an `alarm` kind with an alarm-clock symbol ("Alarm set", "Wecker gestellt"). An older app shows it as a plain card.

## Consequences

- "Do I need an umbrella tomorrow?" is a talker reply of about 1 to 2 s, with no helper and no tool call. The forecast costs one HTTP round trip every 45 minutes or so, and only when the user talks.
- The forecast is for one place. "What's the weather in Rome?" still goes to a helper.
- The place's name and position go to Open-Meteo, nothing else. A user who doesn't want that sets `[weather] enabled = false`.
- The weather is in English inside the block; the talker answers in the user's language. Day names are written by `core/words/dates`, not `strftime`, so the process's locale doesn't change them.
- An alarm rings only while the brain runs and the computer is awake. A closed MacBook lid means no alarm. The docs and Milo's one line say so. A later change could let the app schedule a wake with the user's admin password once, or hand the alarm to the phone.
- The weather service is in `<today>` only with quick actions on, like the calendar.
- Alarms survive a restart; timers still don't (ADR 29).
- Not run on a real Mac: the alarm's chime and line through the real speaker, ringing over a reply, the key press stopping it, and the app's `alarm` card were never seen or heard. The tests use the fake voice and speaker and a fake clock. The Swift code builds and its card text is tested. One manual request to Open-Meteo for Berlin and for "Portland, Oregon" returned a forecast the adapter read correctly. The tests stub the HTTP.
