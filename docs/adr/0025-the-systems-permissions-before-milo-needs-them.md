# 25. The system's permissions, before Milo needs them

Date: 2026-10-31. Status: accepted. The number may change: other ADRs written the same day may take it. Builds on [ADR 12](0012-background-delivery.md) and [ADR 23](0023-stop-for-what-cant-be-undone.md), and follows the boundary of [ADR 27](0027-a-platform-boundary.md).

## Context

The user: "Make sure that everything is very smooth, so how the user will be asked if it's allowed to use Excel and so on. Everything has to be very smooth."

Milo's own questions were reworked in ADR 22 and 23. What was still rough was macOS's:

- The first script in an app brought up "Milo wants access to control Microsoft Excel" in the middle of a task, with nothing said first. The prompt's own line came from `NSAppleEventsUsageDescription` and talked about mail and notes, whatever the app.
- A Don't Allow came back to the worker as a script error (-1743). The brain turned it into "tell the user to switch on Excel in System Settings", and the user saw nothing they could click.
- Clicks and screenshots without Accessibility or Screen Recording failed only once the app tried them.
- In a test the same day, a script made Excel save outside its sandbox. Excel put up "Grant File Access" and sat blocked until someone clicked it.

## Decision

**The brain speaks of needs, the app knows the system.** `core/access.py` has three needs, `control` (one app, by scripts), `ui` (other apps' windows) and `screen` (pixels). It has four answers: `yes`, `no`, `ask` (the system will ask the user once) and `unknown` (an older app, an app that isn't installed). The app answers three `app_request` ops: `access.check`, `access.request` and `access.places`. Its answer also gives the system's name, the switch's name and the yes button ("macOS", "Accessibility", "Allow"), so Milo's words come out right without the brain naming macOS. A Windows or Linux app answers the same ops its own way. `tests/test_portability.py` (ADR 27) holds `core/access.py` and `services/access.py` to that, with no new allowlist lines.

**Before the system asks** (`services/access.py`, `AccessGate`):

1. Milo has passed his own checks and the user said yes where he asked. The gate checks `control` for the app the action scripts. For Automation the app starts an app that isn't running, out of sight, because macOS can only answer for a running app. The script would start it a moment later anyway.
2. `yes`: nothing is shown, then or ever. The yes is kept for the life of the brain.
3. `ask`: Milo says one line, "macOS will ask once whether I may use Microsoft Excel. Click Allow." It shows in the bubble and, unless the user is talking or answering something, is spoken aloud. The task shows a step, "Asking to use Microsoft Excel". After 1.5 s the app has macOS ask (`AEDeterminePermissionToAutomateTarget` with the prompt), and the brain waits for the answer. While macOS's question is up, the app's stop-on-touch check is off, so the click on Allow can't stop Milo.
4. `no`: Milo says "Okay, I won't use Microsoft Excel. If you change your mind, Fix it shows the switch." If the user had turned it down before, he says "I'm not allowed to use Microsoft Excel yet." The bubble's Fix it opens Privacy & Security › Automation, where Excel's switch sits under Milo. macOS has no link to one app's row. The worker hears that the user didn't allow it, not to try that app again this task, and to finish another way if there is one or say what is left. A task shows each refusal once, however many steps hit it.
5. `unknown`: the work goes on as before.

The check comes after Milo's own yes on purpose. An action he refuses (a password script) or one the user turns down never starts an app or brings up macOS's question. `sheet_write` is the exception. Its look at the sheet already scripts the app, so that look waits for the check.

**Clicks, typing and screenshots.** Before the first action that needs them, the gate checks `ui` (Accessibility) or `screen` (Screen Recording). If one is missing, Milo says "To work in other apps' windows I need Accessibility. Fix it shows where to switch it on." Fix it opens the permissions window, which already has the drag tile, the stale-entry repair and the restart for Screen Recording. Nothing is described or clicked. The worker is pointed at the script tools, or at `window_text` for a screenshot. Scripts no longer need Accessibility: `MacHands` used to want it even for describing a script.

**Mail and Notes.** The connection tools run their own scripts in another process, so they ask the brain over the tool socket (`{"op": "access", "app": "Mail"}`) before their first script in an app, and get the same line and the same Fix it. Only Mail and Notes are accepted there, so no caller can start another app or bring up a prompt through it. The fake connections never ask.

**Never "Grant File Access".** Before it runs a script, `MacHands` looks for one that saves or exports (`SandboxGuard`). If the script names a sandboxed app and a path outside that app's own places, it doesn't run, and the worker is told why. A path counts as outside if it is a POSIX or HFS literal, or a folder taken from `path to`. It is told to leave the document open for the user to save, or to save a working copy in the app's container. The places come from the app's signed entitlements: the container, group containers, Downloads if the app is entitled to it, and temporary exceptions (`MacAppAccess.places`). Snapshots and working copies an app writes for Milo go there. The brain gets them through `AccessGate.places(app)`, and Milo only opens them again through the same app. Milo himself reading another app's container would bring up macOS's "access data from other apps" question.

**Seeing it.** The app remembers every yes and no macOS gave (`ControlledApps`, in UserDefaults), because macOS lets no app read its Automation list. The menu bar's "Apps Milo may control" and a card in the permissions window list them, ticked or "not allowed", and look again without prompting each time they open. Changing one opens System Settings. The prompt's own line now fits any app: "Milo works in this app only when you ask him to, like filling in a sheet or writing a note, and you see each step. He asks before anything that can't be undone."

## Consequences

- The first Excel task still gets macOS's one question, but it never comes as a surprise and never blocks a script halfway. A 30 s script limit used to run out while the prompt waited.
- A `yes` is trusted until a script is refused. Then the old error (-1743 in `services/hands.py`) goes through the gate too, so it gets the same Fix it note and the cached yes is dropped. That regex is pre-existing macOS knowledge in a core service, listed in ADR 27's allowlist. The app could later report the refusal as `{"refused": "control"}` instead.
- Starting an app to ask about it means a Don't Allow can leave Excel open and unused. The script would have started it either way.
- The sandbox guard is a word list, like `risk.py`. A path built in a variable gets through. One script that names a sandboxed app and also saves through another app's path is refused, which errs towards no dialog.
- A user who asks to save into Documents from Excel now gets "leave it open and save it yourself" instead of macOS's dialog. That is the trade the user asked for. A later change could save a copy in the container and have Excel open the save panel at the right folder.
