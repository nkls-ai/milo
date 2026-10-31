# 28. Open at once, keys only into their app, and the language of the message

Date: 2026-10-31. Status: accepted. The number may change: other ADRs written the same day may take it. Changes [ADR 11](0011-helpers-and-the-orchestrator.md) (the talker opens things itself) and [ADR 14](0014-scripts-milo-writes-and-short-questions.md) (opening comes before scripts in the worker's routes).

## Context

The user said, in English, "open Chrome for me and go on YouTube". Milo answered "Schön zu hören, dass es flüssiger läuft. Ich öffne Chrome und gehe auf YouTube." and started a careful screen helper. That helper took 45 s and 226,938 input tokens, and Chrome never showed YouTube:

- The talker had no way to open anything, so even this went to a Codex helper.
- The helper opened Chrome (which had no window), then pressed ⌘T and ⌘N. `key` went to whatever app was in front: first T3 Code, then Milo himself. Milo asked "May I use T3 Code (Beta) for this?" and "May I use Milo for this?". The second try used a script, which asked "Run a script in Google Chrome?". There was no tool to open a web page.
- The reply rules only said "Reply in the language the user speaks". The recalled episodes were German, so the model answered in German.
- The tokens: Codex runs MCP tools from JavaScript (`exec`) and doesn't list them up front. The helper's first step listed them all, and Codex put the milo-mac server's 1,600-character instructions in front of each of the 13 matching descriptions: an output of 11,636 tokens. Each of the 9 model calls after that sent about 26,000 tokens again.

The user's bar: no slower than doing it themselves. Milo says "Opening YouTube in Chrome" and Chrome is in front showing youtube.com within a second or two, with no helper and no question.

## Decision

**The talker opens things itself.** It writes `<open app="Google Chrome" url="https://www.youtube.com"/>`, `<open app="Notes"/>` or `<open path="~/Downloads"/>` right after its emotion tag, then one short line. `ReplyParser` reads the tag as it streams. `LiveTalk` hands it to `Opener` at once, before the reply has ended, and `Opener` sends the app `open_url`, `open_app` or `open_file` through the hands path (`AppHands`), outside any helper's task. No harness turn, no `HandsService` task, no question. The log says how long it took from the user's words (`milo.open: opened … in 0.4s, 1.3s after the user's words`). A site the user only names ("YouTube") is its address (`core/opening.SITES`, else `www.<name>.com`).

**What may open without a yes.** Opening changes nothing, so ADR 22's rule holds: it never asks for its own sake. But an address can carry data to someone else, and outside text can name one. So:

- An app always opens.
- An address opens at once when the conversation read no outside text, or when the user's own words name its site. After outside text only a site's front page at its own address counts as named: the SITES address of a name the user said ("go on YouTube" for www.youtube.com), the address the user said ("open bbc.co.uk"), or www.<word>.com for a word they said ("open figma"). A path, query or fragment always asks then, and so does any other host under a familiar word (`youtube.evil`, `youtube.com.evil.example`): outside text could have written it to carry what Milo read to its server.
- A file or folder opens at once only in a conversation without outside text. After outside text it always asks: a name said in passing can't tell which file a page put there.
- Otherwise Milo asks "Open evil.example?" after the reply (`Approvals.confirm`).
- Only http and https open as addresses, in the brain (`resolve_url`) and again in the app (`OpenGuard.refuses(url:)`): another scheme can run a shortcut or open a setting. A file that would run code (an app, a `.command`, an installer, an AppleScript, any bundle or plug-in, even one renamed without its extension) never opens (`OpenGuard.refuses(path:)`), and neither does an internet location (`.webloc`, `.inetloc`, `.url`, `.mailloc`), which opens whatever address it holds. The check is on the file a link or Finder alias points to, and that file is what opens. A plain folder and a document package (a Pages file) open. A file always opens in its own app, never one the model names: a terminal runs the text file it opens. A page opens in a named app only if the system says that app opens web pages.

**Opening in the app.** `open_app`, `open_url` and `open_file` go through Launch Services (`/usr/bin/open`), which activates the app even while Milo isn't the active app and asks a running app with no windows for a new one, as a Dock click does. Then the app waits at most 2 s until that app is in front with a window on screen (`MacHands.arrived`) and answers `{"app", "bundle", "front"}`. `NSRunningApplication.activate()` alone is what left Chrome windowless.

**Helpers get `open_url`.** A milo-mac tool with `url` and an optional `app`, no question, `acts`. A careful helper's `open_url` asks, since it may have read the address. The worker's routes start with `open_url` and `open_app`, "never keys, clicks or a script".

**Keys, typing and clicks go only into their app.** `click`, `type` and `key` take `app`. Without it they go to the app the task last opened or named; with neither they are refused ("Say which app this is for"). Before describing the target, `HandsService` asks the app to `focus_app`: it activates that app (Launch Services if `activate()` is ignored) and waits at most 2 s until it is in front. If the target `describe` then finds is Milo's own window (`"milo": true`) or another app, the action is refused with words for the worker, before any question. Milo never asks to use T3 Code, or himself.

**Milo's own window is never a target.** Any acting tool whose target is Milo's own window (his bubble, his Yes and Allow buttons, his conversation) is refused in the brain before a question, so no question names Milo and no Allow or Allow always can put him into `allowed_apps`, as happened in this run (the user removed T3 Code and Milo from their config by hand). The app refuses again: it never presses, fills in or types into an element of its own process (`MacHands.notMilo`). The brain knows Milo's window by the `milo` flag in `describe`, not by a bundle id, which the brain's core may not name (ADR 27).

**The language of the message.** Each user message's stamp says its language: `[Saturday 2026-10-31 12:56, frontmost app: T3 Code, language: English]`. It comes from the transcriber (Scribe's `language_code` with `include_language_detection`, Whisper's detection on its last full pass), else from the words (`core/language.detect`, German and English by their short words), else from the message before, so "okay" keeps the conversation's language. The reply rules say: reply in exactly that language, even when memories, task results or earlier turns are in another one, and write a task's first sentence and title in it. `SpokenLanguage` holds it for the turn: a helper is told to write its `say` in it, and the questions Milo writes himself are asked in German when the user speaks German: every screen question (`confirm_question`, with the risk reasons as German phrases), borrowing the mouse or keyboard, starting or changing a task, remember, remind, open, and Approvals' own lines (no answer, money needs a click, "all of it is in the Milo window"). A task's question is its first sentence, which the model now writes in the user's language. The questions the connection tools send from their own process ("Write a draft to Anna?"), routines, Undo and the system-permission lines stay English for now.

**A script question in plain words.** "Run a script in Microsoft Excel? It's in my window." becomes "May I work in Microsoft Excel directly? You can read the steps in my window." ("Darf ich direkt in Microsoft Excel arbeiten? Die Schritte stehen in meinem Fenster."), with "It could send." in between when the script names something risky.

**What counts as asking for work.** `asks_for_work` (ADR 22's auto mode) missed real requests: "Yes, open Chrome and YouTube.", "Remind me to call Anna tomorrow at 9", "Take notes of this meeting", "Can you summarize the PDF". It now knows open, go, show, play, send, remind, check, find, summarize, start, stop, set and take, and öffne, zeig, spiel, schick, erinner and stell, and "can you …" or "kannst du …" with such a verb is a request even though it is phrased as a question. "Can you see my screen?" and "what can you open?" still aren't.

**Smaller screen helpers.** The milo-mac instructions are now 750 characters instead of 1,580, since Codex repeats them in front of every tool. A screen helper's first prompt names its tools ("Your screen tools are on the milo-mac server: open_url, open_app, …. Call them directly"), so it has no reason to list them.

## Consequences

- "Open Chrome and go to YouTube" is one talker turn: about 1 s to its first word (measured before this change, `first delta 0.85s`), the page opening while Milo speaks. Not measured end to end on the real screen: the tests don't click around the user's Mac.
- `focus_app` brings the app forward for every key, typing or click whose app isn't in front, even with `[hands] show_window` off. That is the point: a keystroke must land in its app. A user who clicks away mid-task gets the app back on the next keystroke.
- A key the worker meant for an app it never named fails once with words it can fix. Old worker habits (press ⌘T in whatever is in front) stop working on purpose.
- The language guess knows German and English words only. Other languages rely on the transcriber, and typed text in them goes without a language line, as before.
- Scribe's `include_language_detection` is documented but wasn't tried against the live service here. If ElevenLabs refused it, talking would fall back to Whisper with the "transcribing on this Mac" note.
- Codex still runs in its JavaScript mode and may list tools anyway. The prompt only makes that unnecessary. Turning code mode off is a harness change left for later.
