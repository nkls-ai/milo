"""Plain words for Milo's connection tools: step titles for the Milo window and the questions he asks first.

Pure functions, shared by the brain (questions for app work), the connections server and the activity parser.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def first_name(address: str) -> str:
    """'Anna Schmidt <anna@example.com>' or 'anna.schmidt@example.com' -> 'Anna'."""
    address = address.strip()
    name = address.split("<")[0].strip().strip('"') if "<" in address else ""
    if not name:
        name = re.split(r"[._+-]", address.split("@")[0])[0]
    word = name.split()[0] if name.split() else ""
    return word[:1].upper() + word[1:]


def _quoted(text: object, n: int = 30) -> str:
    text = " ".join(str(text or "").split())
    return f"“{text if len(text) <= n else text[:n - 1].rstrip() + '…'}”"


def _to(args: dict) -> str:
    to = args.get("to") or []
    names = [first_name(str(a)) for a in (to if isinstance(to, list) else [to]) if str(a).strip()]
    return " and ".join(n for n in names[:2] if n)


def title(tool: str, args: dict) -> str | None:
    """The title for one of Milo's tools, or None if `tool` isn't one of them."""
    match tool:
        case "calendar_events":
            q = args.get("query")
            return f"Looking in your calendar for {_quoted(q)}" if q else "Looking in your calendar"
        case "calendar_add_event":
            return f"Putting {_quoted(args.get('title'))} in your calendar"
        case "reminders_list":
            return "Looking at your reminders"
        case "reminders_add":
            return f"Adding the reminder {_quoted(args.get('title'))}"
        case "reminders_complete":
            return "Ticking off a reminder"
        case "mail_search":
            q = args.get("query")
            return f"Looking through your mail for {_quoted(q)}" if q else "Looking through your mail"
        case "mail_read":
            return "Reading an email"
        case "mail_draft":
            to = _to(args)
            if args.get("reply_to"):
                return f"Writing a reply to {to}" if to else "Writing a reply"
            if args.get("forward"):
                return f"Passing on an email to {to}" if to else "Passing on an email"
            return f"Writing a draft to {to}" if to else "Writing a draft"
        case "notes_search":
            q = args.get("query")
            return f"Looking through your notes for {_quoted(q)}" if q else "Looking through your notes"
        case "notes_read":
            return "Reading a note"
        case "notes_create":
            return f"Writing the note {_quoted(args.get('title'))}"
        case "notes_append":
            return "Adding to a note"
        case "shortcuts_list":
            return "Checking your shortcuts"
        case "shortcuts_run":
            return f"Running your shortcut {_quoted(args.get('name'))}"
        case "files_find":
            return f"Looking for files named {_quoted(args.get('name'))}"
        case "files_search":
            return f"Searching your files for {_quoted(args.get('text'))}"
        case "files_read":
            name = Path(str(args.get("path") or "")).name
            return f"Reading {name}" if name else "Reading a file"
    return None


KINDS = {"calendar": "app", "reminders": "app", "mail": "app", "notes": "app", "shortcuts": "app",
         "files": "search"}


def kind(tool: str) -> str:
    """The activity icon for one of Milo's tools."""
    if tool.startswith(("files_read", "mail_read", "notes_read")):
        return "read"
    if tool.endswith(("_add_event", "_add", "_complete", "_draft", "_create", "_append")):
        return "edit"
    return KINDS.get(tool.split("_")[0], "tool")


def when(value: object) -> str:
    """'2026-11-05T15:00' -> 'Thursday 5 November at 15:00'. Unparseable text comes back as it is."""
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{dt:%A} {dt.day} {dt:%B}" + (f" at {dt:%H:%M}" if (dt.hour, dt.minute) != (0, 0) else "")


def question(tool: str, args: dict) -> str:
    """The yes-or-no question Milo asks before `tool` when its action level is ask_first."""
    match tool:
        case "calendar_add_event":
            return f"Put {_quoted(args.get('title'), 50)} in your calendar on {when(args.get('start'))}?"
        case "reminders_add":
            due = f" for {when(args['due'])}" if args.get("due") else ""
            return f"Add the reminder {_quoted(args.get('title'), 50)}{due}?"
        case "reminders_complete":
            return "Tick off that reminder?"
        case "mail_draft":
            to = args.get("to") or []
            everyone = ", ".join(str(a).strip() for a in (to if isinstance(to, list) else [to]))
            return (f"Write a draft to {everyone}? It stays in Mail until you send it." if everyone.strip()
                    else "Write a reply draft? It stays in Mail until you send it.")
        case "notes_create":
            return f"Make a new note called {_quoted(args.get('title'), 50)}?"
        case "notes_append":
            return "Add this to your note?"
        case "shortcuts_run":
            given = f" with {_quoted(args['input'], 80)}" if args.get("input") else ""
            return f"I'm about to run your shortcut {_quoted(args.get('name'), 50)}{given}. Go ahead?"
    return (title(tool, args) or "Go ahead") + "?"
