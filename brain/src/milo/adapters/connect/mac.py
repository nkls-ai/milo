"""The real connections on this Mac: Calendar and Reminders through Milo.app, Mail and Notes through
AppleScript, the `shortcuts` command, and Spotlight for files."""

from __future__ import annotations

import html
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from milo.core.control import Protected
from milo.core.ports import Connections
from milo.core.registry import CONNECTIONS, AdapterContext, options_from
from milo.core.types import ToolError
from milo.memory.workspace import Workspace
from milo.transport.tool_client import BrainClient

from . import _files, _osascript
from ._osascript import records

SHORTCUT_TIMEOUT_S = 120
MDFIND_TIMEOUT_S = 20
MDFIND_MAX = 400


@dataclass(frozen=True)
class MacOptions:
    files_scope: str = "~"


def _iso(dt: datetime | None) -> str:
    return dt.isoformat(timespec="minutes") if dt is not None else ""


class AppCalendar:
    """EventKit in Milo.app, reached through the brain. The brain applies the action level itself."""

    approves_itself = True

    def __init__(self, brain: BrainClient):
        self._brain = brain

    def _app(self, name: str, args: dict) -> Any:
        return self._brain.request({"op": "app", "name": name, "args": args})

    def events(self, start: datetime, end: datetime, query: str = "") -> list[dict]:
        return self._app("calendar.events", {"start": _iso(start), "end": _iso(end), "query": query})

    def add_event(self, title: str, start: datetime, end: datetime, location: str = "", notes: str = "",
                  calendar: str = "") -> dict:
        return self._app("calendar.add_event", {"title": title, "start": _iso(start), "end": _iso(end),
                                                "location": location, "notes": notes, "calendar": calendar})


class AppReminders:
    approves_itself = True

    def __init__(self, brain: BrainClient):
        self._brain = brain

    def _app(self, name: str, args: dict) -> Any:
        return self._brain.request({"op": "app", "name": name, "args": args})

    def list(self, query: str = "", include_done: bool = False) -> list[dict]:
        return self._app("reminders.list", {"query": query, "include_done": include_done})

    def add(self, title: str, due: datetime | None = None, notes: str = "", list_name: str = "") -> dict:
        return self._app("reminders.add", {"title": title, "due": _iso(due), "notes": notes, "list": list_name})

    def complete(self, id: str) -> dict:
        return self._app("reminders.complete", {"id": id})


# Both mailboxes are the unified ones across accounts. Messages are found again by their Message-ID header.
_MAIL_FIND = """
on findMessage(mid)
	tell application "Mail"
		repeat with box in {inbox, sent mailbox}
			set found to (every message of box whose message id is mid)
			if found is not {} then return item 1 of found
		end repeat
	end tell
	error "not found" number 4040
end findMessage
"""

_MAIL_SEARCH = """
on run argv
	set q to item 1 of argv
	set lim to (item 2 of argv) as integer
	set US to character id 31
	set RS to character id 30
	set out to ""
	tell application "Mail"
		set boxes to {inbox, sent mailbox}
		set labels to {"inbox", "sent"}
		repeat with i from 1 to 2
			set found to (every message of (item i of boxes) whose subject contains q or sender contains q)
			set n to 0
			repeat with m in found
				if n ≥ lim then exit repeat
				set out to out & (message id of m) & US & (sender of m) & US & (subject of m) & US & ¬
					((date received of m) as «class isot» as string) & US & (item i of labels) & RS
				set n to n + 1
			end repeat
		end repeat
	end tell
	return out
end run
"""

_MAIL_READ = _MAIL_FIND + """
on run argv
	set US to character id 31
	set m to findMessage(item 1 of argv)
	tell application "Mail"
		set toList to ""
		repeat with r in (to recipients of m)
			set toList to toList & (address of r) & ", "
		end repeat
		return (sender of m) & US & toList & US & (subject of m) & US & ¬
			((date received of m) as «class isot» as string) & US & (content of m)
	end tell
end run
"""

# Opens the draft in Mail and saves it to Drafts. There is no `send` here, on purpose.
_MAIL_DRAFT = _MAIL_FIND + """
on run argv
	set toText to item 1 of argv
	set subj to item 2 of argv
	set body to item 3 of argv
	set mid to item 4 of argv
	set fid to item 5 of argv
	tell application "Mail"
		if mid is not "" then
			set m to reply (my findMessage(mid)) with opening window
			set content of m to body
		else if fid is not "" then
			-- the content is left alone so the original and its attachments stay as Mail made them
			set m to forward (my findMessage(fid)) with opening window
		else
			set m to make new outgoing message with properties {subject:subj, content:body, visible:true}
		end if
		if toText is not "" then
			set AppleScript's text item delimiters to linefeed
			set addresses to text items of toText
			set AppleScript's text item delimiters to ""
			repeat with addr in addresses
				tell m to make new to recipient at end of to recipients with properties {address:(addr as text)}
			end repeat
		end if
		try
			save m
		end try
		activate
		return subject of m
	end tell
end run
"""


class AppleMail:
    def search(self, query: str, limit: int = 20) -> list[dict]:
        out = _osascript.run(_MAIL_SEARCH, query, str(limit), app="Mail")
        found = [{"id": r[0], "from": r[1], "subject": r[2], "date": r[3][:16], "mailbox": r[4]}
                 for r in records(out) if len(r) >= 5]
        found.sort(key=lambda m: m["date"], reverse=True)
        return found[:limit]

    def read(self, id: str) -> dict:
        r = _osascript.run(_MAIL_READ, id, app="Mail").split(_osascript.US, 4)
        if len(r) < 5:
            raise ToolError("I couldn't read that email.")
        return {"id": id, "from": r[0], "to": r[1].rstrip(", "), "subject": r[2], "date": r[3][:16], "text": r[4]}

    def draft(self, to: list[str], subject: str, body: str, reply_to: str = "") -> dict:
        return self._draft(to, subject, body, reply_to, "")

    def forward(self, id: str, to: list[str]) -> dict:
        return self._draft(to, "", "", "", id)

    @staticmethod
    def _draft(to: list[str], subject: str, body: str, reply_to: str, forward: str) -> dict:
        saved = _osascript.run(_MAIL_DRAFT, "\n".join(to), subject, body, reply_to, forward, app="Mail")
        return {"draft": True, "sent": False, "subject": saved or subject, "to": to,
                "where": "Open in Mail for the user to check and send."}


_NOTES_SEARCH = """
on run argv
	set q to item 1 of argv
	set lim to (item 2 of argv) as integer
	set US to character id 31
	set RS to character id 30
	set out to ""
	tell application "Notes"
		try
			set found to (every note whose name contains q or plaintext contains q)
		on error
			set found to (every note whose name contains q)
		end try
		set n to 0
		repeat with nt in found
			if n ≥ lim then exit repeat
			if not (password protected of nt) then
				set out to out & (id of nt) & US & (name of nt) & US & (name of container of nt) & US & ¬
					((modification date of nt) as «class isot» as string) & RS
				set n to n + 1
			end if
		end repeat
	end tell
	return out
end run
"""

_NOTES_READ = """
on run argv
	set US to character id 31
	tell application "Notes"
		set nt to note id (item 1 of argv)
		if password protected of nt then error "That note is locked, so I left it alone." number 4041
		return (name of nt) & US & (name of container of nt) & US & (plaintext of nt)
	end tell
end run
"""

_NOTES_CREATE = """
on run argv
	set US to character id 31
	set html to item 1 of argv
	set folderName to item 2 of argv
	tell application "Notes"
		if folderName is "" then
			set nt to make new note with properties {body:html}
		else
			set nt to make new note at folder folderName with properties {body:html}
		end if
		return (id of nt) & US & (name of nt)
	end tell
end run
"""

# Rewriting the body of a note can drop its pictures, so notes with attachments are left alone.
_NOTES_APPEND = """
on run argv
	tell application "Notes"
		set nt to note id (item 1 of argv)
		if password protected of nt then error "That note is locked, so I left it alone." number 4041
		if (count of attachments of nt) > 0 then error "That note has pictures or files in it, so I left it alone. I can make a new note instead." number 4041
		set body of nt to (body of nt) & (item 2 of argv)
		return name of nt
	end tell
end run
"""


def _note_html(text: str) -> str:
    return "".join(f"<div>{html.escape(line) or '<br>'}</div>" for line in text.splitlines())


class AppleNotes:
    def search(self, query: str, limit: int = 20) -> list[dict]:
        out = _osascript.run(_NOTES_SEARCH, query, str(limit), app="Notes")
        return [{"id": r[0], "title": r[1], "folder": r[2], "modified": r[3][:16]} for r in records(out) if len(r) >= 4]

    def read(self, id: str) -> dict:
        r = _osascript.run(_NOTES_READ, id, app="Notes").split(_osascript.US, 2)
        if len(r) < 3:
            raise ToolError("I couldn't read that note.")
        return {"id": id, "title": r[0], "folder": r[1], "text": r[2]}

    def create(self, title: str, body: str, folder: str = "") -> dict:
        content = f"<div><h1>{html.escape(title)}</h1></div>" + _note_html(body)
        r = _osascript.run(_NOTES_CREATE, content, folder, app="Notes").split(_osascript.US, 1)
        return {"id": r[0], "title": r[-1]}

    def append(self, id: str, text: str) -> dict:
        title = _osascript.run(_NOTES_APPEND, id, _note_html(text), app="Notes")
        return {"id": id, "title": title, "appended": True}


class ShortcutsApp:
    def list(self) -> list[str]:
        return [line for line in self._run(["shortcuts", "list"], timeout_s=30).splitlines() if line.strip()]

    def run(self, name: str, input_text: str = "") -> str:
        if name not in self.list():
            raise ToolError(f"There's no shortcut called “{name}”.")
        with tempfile.TemporaryDirectory(prefix="milo-shortcut-") as tmp:
            out = Path(tmp) / "output.txt"
            cmd = ["shortcuts", "run", name, "--output-path", str(out), "--output-type", "public.plain-text"]
            if input_text:
                given = Path(tmp) / "input.txt"
                given.write_text(input_text, encoding="utf-8")
                cmd += ["--input-path", str(given)]
            self._run(cmd, timeout_s=SHORTCUT_TIMEOUT_S)
            return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""

    @staticmethod
    def _run(cmd: list[str], timeout_s: float) -> str:
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise ToolError("The shortcut took too long, so I stopped waiting.") from None
        except OSError:
            raise ToolError("I couldn't reach the Shortcuts app.") from None
        if done.returncode != 0:
            raise ToolError("The shortcut didn't work: " + (done.stderr.strip().splitlines() or ["no reason given"])[-1])
        return done.stdout


class SpotlightFiles:
    def __init__(self, scope: Path, protected: Protected | None = None):
        self.scope = scope
        self.protected = protected
        """Milo's control files, which these tools never list, read or move (ADR 0020)."""

    def find(self, name: str, limit: int = 20) -> list[dict]:
        return _files.newest(self._mdfind(["-name", name]), self.scope, limit, self.protected)

    def search(self, text: str, limit: int = 20) -> list[dict]:
        query = " ".join(text.translate({ord(c): " " for c in "\"'\\()=<>*$"}).split())
        if not query:
            raise ToolError("Say what words to look for.")
        return _files.newest(self._mdfind([query]), self.scope, limit, self.protected)

    def read(self, path: str, max_chars: int = 20000) -> dict:
        return _files.read(_files.checked(path, self.scope, self.protected), max_chars)

    def list(self, folder: str, name: str = "", limit: int = 20) -> list[dict]:
        return _files.listing(folder, self.scope, name, limit, self.protected)

    def move(self, paths: list[str], folder: str) -> dict:
        return _files.move(paths, folder, self.scope, self.protected)

    def _mdfind(self, query: list[str]) -> list[Path]:
        try:
            done = subprocess.run(["mdfind", "-onlyin", str(self.scope), *query], capture_output=True, text=True,
                                  timeout=MDFIND_TIMEOUT_S, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            raise ToolError("Searching your files took too long.") from None
        return [Path(line) for line in done.stdout.splitlines()[:MDFIND_MAX] if line]


@CONNECTIONS.register("mac")
def _mac(options: Mapping[str, Any], ctx: AdapterContext) -> Connections:
    o = options_from(MacOptions, options, "connections.mac")
    brain = BrainClient(Workspace(ctx.home).tools_socket_path)
    return Connections(calendar=AppCalendar(brain), reminders=AppReminders(brain), mail=AppleMail(),
                       notes=AppleNotes(), shortcuts=ShortcutsApp(),
                       files=SpotlightFiles(Path(o.files_scope).expanduser().resolve(), Protected(ctx.home)))
