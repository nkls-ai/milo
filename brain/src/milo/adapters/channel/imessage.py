"""iMessage, experimental: the owner messages their own number or Apple ID ("message yourself") and Milo on
the Mac answers in that chat.

- **Reading** polls `~/Library/Messages/chat.db` read-only. macOS only lets Milo read it with Full Disk
  Access (System Settings › Privacy & Security › Full Disk Access › Milo). Without it Milo says so and
  Telegram stays the way to go.
- **Sending** asks Messages through AppleScript, only ever to the one handle in config.toml. macOS asks
  once whether Milo may control Messages.
- Phone and Mac share the Apple ID, so the owner's messages and Milo's both show up as "from me" in that
  chat. Everything Milo sends starts with an invisible separator (U+2063), which tells them apart.

Not verified against the real Messages app (see docs/research/messaging.md): built from how chat.db and
other tools work, and tested against a made-up chat.db.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo.core.registry import CHANNELS, AdapterContext, ConfigError, options_from
from milo.core.types import ChannelError, Inbound

log = logging.getLogger("milo.imessage")

MARK = "⁣"
"""Starts every message Milo sends, so he never answers himself."""
BATCH = 50
NO_ACCESS = ("Milo can't read your messages. To use iMessage, allow Milo in System Settings › Privacy & Security "
             "› Full Disk Access, then restart Milo. Or use Telegram, which needs no permission.")
_HANDLE = re.compile(r"\+?[\d ()-]{6,20}|[^@\s]+@[^@\s]+\.[^@\s]+")
_SEND_TEXT = ('on run argv\n'
              'tell application "Messages"\n'
              'set target to participant (item 2 of argv) of (1st account whose service type = iMessage)\n'
              'send (item 1 of argv) to target\n'
              'end tell\nend run')
_SEND_FILE = ('on run argv\n'
              'tell application "Messages"\n'
              'set target to participant (item 2 of argv) of (1st account whose service type = iMessage)\n'
              'send (POSIX file (item 1 of argv)) to target\n'
              'end tell\nend run')

Runner = Callable[[Sequence[str]], Awaitable[tuple[int, str]]]
"""Runs osascript with these arguments: (exit code, stderr)."""


@dataclass(frozen=True)
class IMessageOptions:
    handle: str = ""
    """Your own phone number (+49 170 1234567) or Apple ID email: the chat Milo reads and writes."""
    database: str = "~/Library/Messages/chat.db"
    poll_s: float = 3.0

    def __post_init__(self):
        if not _HANDLE.fullmatch(self.handle.strip()):
            raise ConfigError("[messages.imessage] handle must be your own phone number or Apple ID email")
        if not 1 <= self.poll_s <= 60:
            raise ConfigError("[messages.imessage] poll_s must be from 1 to 60")


def handle_key(handle: str) -> str:
    """A phone number without spaces and dashes, an email in lower case: how chat.db spells them."""
    handle = handle.strip()
    return handle.lower() if "@" in handle else re.sub(r"[\s()-]", "", handle)


def decode_body(blob: bytes | None) -> str:
    """The text in a message's `attributedBody`, an NSAttributedString in Apple's typedstream format, which
    recent macOS uses instead of the `text` column. "" when there is none."""
    if not blob:
        return ""
    start = blob.find(b"NSString")
    if start < 0:
        return ""
    plus = blob.find(b"+", start)
    if plus < 0 or plus + 1 >= len(blob):
        return ""
    size, at = blob[plus + 1], plus + 2
    if size == 0x81:
        size, at = int.from_bytes(blob[at:at + 2], "little"), at + 2
    elif size == 0x82:
        size, at = int.from_bytes(blob[at:at + 4], "little"), at + 4
    return blob[at:at + size].decode("utf-8", "replace")


async def osascript(args: Sequence[str]) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec("/usr/bin/osascript", *args, stdin=asyncio.subprocess.DEVNULL,
                                                   stdout=asyncio.subprocess.DEVNULL,
                                                   stderr=asyncio.subprocess.PIPE)
    try:
        _, err = await asyncio.wait_for(process.communicate(), 60)
    except TimeoutError:
        process.kill()
        return 1, "Messages didn't answer"
    return process.returncode or 0, err.decode(errors="replace")


class IMessageChannel:
    """The Channel port on Messages.app. Text and files go only to `handle`; see the module docstring."""

    name = "imessage"
    label = "iMessage"

    def __init__(self, handle: str, database: Path, state_path: Path, *, poll_s: float = 3.0,
                 run: Runner = osascript):
        self._handle = handle.strip()
        self._key = handle_key(handle)
        self._database = database
        self._state_path = state_path
        self._poll_s = poll_s
        self._run = run
        self._last = _load_last(state_path)

    async def start(self) -> None:
        try:
            newest = await asyncio.to_thread(self._newest)
        except sqlite3.Error as e:
            log.warning("can't read chat.db: %s", type(e).__name__)
            raise ChannelError(NO_ACCESS) from None
        if self._last is None or self._last > newest:
            self._last = newest  # never answer what came before Milo was switched on
            _save_last(self._state_path, newest)
        log.info("imessage ready")

    async def receive(self) -> list[Inbound]:
        await asyncio.sleep(self._poll_s)
        try:
            rows = await asyncio.to_thread(self._since, self._last or 0)
        except sqlite3.Error as e:
            raise ChannelError(f"Can't read your messages any more ({type(e).__name__}). {NO_ACCESS}") from None
        if not rows:
            return []
        self._last = max(row[0] for row in rows)
        _save_last(self._state_path, self._last)
        out = []
        for _, text, body, attachments in rows:
            text = text or decode_body(body)
            if text.startswith(MARK):
                continue  # Milo's own
            out.append(Inbound(chat=self._handle, sender=self._key, text=text, private=True,
                               attachments=int(bool(attachments))))
        return out

    async def send(self, chat: str, text: str) -> None:
        self._only_owner(chat)
        await self._osascript(_SEND_TEXT, MARK + text.strip())

    async def ask(self, chat: str, id: str, question: str) -> None:
        await self.send(chat, f"{question}\n\nAnswer yes or no.")

    async def typing(self, chat: str) -> None:
        pass  # Messages has no way to show it from a script

    async def send_file(self, chat: str, path: Path, caption: str = "") -> None:
        self._only_owner(chat)
        if caption:
            await self.send(chat, caption)
        await self._osascript(_SEND_FILE, str(path))

    async def acknowledge(self, inbound: Inbound, text: str = "") -> None:
        pass  # no buttons in iMessage

    async def close(self) -> None:
        pass

    def _only_owner(self, chat: str) -> None:
        if chat != self._handle:
            raise ChannelError("Milo only writes to your own iMessage chat.")

    async def _osascript(self, script: str, value: str) -> None:
        code, err = await self._run(["-e", script, "--", value, self._handle])
        if code != 0:
            log.warning("messages refused a send (%d)", code)
            if "-1743" in err or "not allowed" in err.lower():
                raise ChannelError("Milo isn't allowed to control Messages. Allow it in System Settings › Privacy "
                                   "& Security › Automation › Milo › Messages.")
            raise ChannelError("Messages couldn't send it.")

    # ---- chat.db, read-only

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f"{self._database.expanduser().as_uri()}?mode=ro", uri=True, timeout=5)

    def _newest(self) -> int:
        with self._connect() as db:
            return int(db.execute("SELECT COALESCE(MAX(ROWID), 0) FROM message").fetchone()[0])

    def _since(self, last: int) -> list[tuple[int, str | None, bytes | None, int]]:
        """The owner's new messages in their own chat: sent from their devices (from me) or, on setups that
        keep both sides, received from their own handle. Reactions and system rows are left out."""
        query = """
            SELECT m.ROWID, m.text, m.attributedBody, m.cache_has_attachments
            FROM message m
            JOIN chat_message_join j ON j.message_id = m.ROWID
            JOIN chat c ON c.ROWID = j.chat_id
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            WHERE m.ROWID > ? AND c.chat_identifier IN (?, ?)
              AND COALESCE(m.associated_message_type, 0) = 0 AND COALESCE(m.item_type, 0) = 0
              AND (m.is_from_me = 1 OR h.id IN (?, ?))
            ORDER BY m.ROWID LIMIT ?"""
        with self._connect() as db:
            rows = db.execute(query, (last, self._handle, self._key, self._handle, self._key, BATCH)).fetchall()
            if not rows:
                # Rows we skip still move the mark, so a busy chat elsewhere isn't read again every poll.
                newest = int(db.execute("SELECT COALESCE(MAX(ROWID), 0) FROM message").fetchone()[0])
                if newest > last:
                    self._last = newest
                    _save_last(self._state_path, newest)
        return [(int(r[0]), r[1], r[2], int(r[3] or 0)) for r in rows]


def _load_last(path: Path) -> int | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("last")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def _save_last(path: Path, last: int) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"last": last}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        log.exception("could not save the imessage mark")


@CHANNELS.register("imessage")
def _imessage(options: Mapping[str, Any], ctx: AdapterContext) -> IMessageChannel:
    o = options_from(IMessageOptions, options, "messages.imessage")
    return IMessageChannel(o.handle, Path(o.database).expanduser(), ctx.state_dir / "imessage.json", poll_s=o.poll_s)
