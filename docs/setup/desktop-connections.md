# Calendar, tasks, mail and notes on Windows and Linux

Milo uses the same connection interfaces on every platform. The Mac adapter
continues to use Calendar, Reminders, Mail and Notes. The shared desktop app
defaults to local file access on Windows and Linux. Choose a connection backend
in `~/Milo/config.toml`, then restart the brain from Milo's tray menu.

## Classic Outlook on Windows

Open **Classic Outlook** and sign in to your normal profile first. This adapter
uses Outlook's COM object model, which **New Outlook does not provide**. It does
not require a separate API key or send your mailbox to another service.

```toml
[connections]
use = "outlook"

[connections.outlook]
calendar = ""
tasks = ""
notes = ""
```

An empty name selects that profile's default folder. A name selects a direct
child of that default Calendar, Tasks or Notes folder. Milo refuses an unknown
folder rather than writing somewhere else. Mail searches the default Inbox and
Sent folders, newest first. Search scans are bounded to avoid freezing Outlook
on a very large mailbox.

The adapter supports calendar searches, appointment creation, moving or deleting
one appointment occurrence, Outlook tasks and completion/undo, mail search and
reading, mail drafts/replies/forwards, and Outlook notes. Drafts are saved and
opened in Outlook for you to check and send. There is no send operation in this
adapter. Recurring calendar changes require the start time of the occurrence;
Milo refuses a request that could change the whole series.

COM initialization and cleanup happen on the thread making each call. Calendar,
mail, tasks and notes share one gateway that serializes their calls. Importing
Milo or constructing the adapters does not start Outlook.

The Outlook object-model contracts are covered by fake-COM tests. A live Outlook
profile is needed to verify the installed Office version and account behavior;
those tests do not touch a user's real mailbox.

## CalDAV on Linux, Windows or Mac

CalDAV connects to a calendar/task service such as a self-hosted Radicale or
Nextcloud instance. Milo uses the same Calendar and Reminders interfaces for it
as for the Mac's built-in apps. The service must support `VEVENT` for calendars
and `VTODO` for tasks; not every calendar provider supports both.

```toml
[connections]
use = "caldav"

[connections.caldav]
url = "https://calendar.example.com/dav/"
username = "you@example.com"
key_ref = "caldav.key"
calendar = "Personal"
tasks = "Personal"
timeout_s = 20
```

Put the service password or app password alone in `~/Milo/secrets/caldav.key`.
Do not put it in the URL, configuration file or chat. Milo checks ownership and
private permissions before reading it. `key_ref` must be a filename inside the
secrets folder. An empty username supports services that need no authentication.

Use the calendar's displayed name. If more than one calendar is available and
you leave the target unnamed, Milo refuses to guess where a new item belongs.
Names must be unique among the service's calendars. Calendar and task-list
targets can be different. The adapter requires HTTPS; plain HTTP is allowed
only for a loopback address, useful for a local service or isolated tests.

Milo can search, create, read, move and delete calendar events, and list, create,
complete, uncomplete and delete tasks. Event searches expand recurring events.
Moving or cancelling one occurrence saves a recurrence override and preserves
the series. Recurring task mutations currently require your calendar app; Milo
refuses to alter the entire task series. Optimistic server preconditions protect
edits and deletes against an item changing between reading and writing.

Calendar and task text from these services is conservatively marked as shared
data. Milo treats it as information rather than instructions, including when it
appears in the day's summary. A new network client is created per call, so
network sessions do not cross executor threads.

CalDAV does not supply mail or notes. Those capabilities are not advertised to
Milo's helpers for this backend. Fake-resource contract tests and isolated
loopback Radicale integration tests cover calendar/task creation, changes,
undo, deletion and individual recurring occurrences. They use disposable data
and a temporary test account, never a user's calendar.

## Local verification

From a checkout with the desktop and development dependencies installed:

```sh
uv run --project brain pytest brain/tests/adapters/test_outlook.py brain/tests/adapters/test_caldav.py
uv run --project brain pytest brain/tests/adapters/test_caldav_e2e.py
```

The second command starts and stops its own local Radicale server. It is skipped
when the optional desktop or development server dependencies are absent.
