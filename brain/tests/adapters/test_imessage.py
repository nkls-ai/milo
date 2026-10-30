"""The experimental iMessage channel against a made-up chat.db and a fake osascript: nothing is sent."""

import asyncio
import os
import sqlite3

import pytest

from milo.adapters.channel.imessage import (MARK, NO_ACCESS, IMessageChannel, IMessageOptions, decode_body,
                                            handle_key)
from milo.core.registry import ConfigError
from milo.core.types import ChannelError

HANDLE = "+49 170 1234567"
KEY = "+491701234567"


def body(text: str) -> bytes:
    """An attributedBody blob the way typedstream stores a short and a long string."""
    raw = text.encode()
    size = bytes([len(raw)]) if len(raw) < 0x80 else b"\x81" + len(raw).to_bytes(2, "little")
    return b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject" \
           b"\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + size + raw + b"\x86\x84\x02iI"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "chat.db"
    with sqlite3.connect(path) as c:
        c.executescript("""
            CREATE TABLE message (ROWID INTEGER PRIMARY KEY, text TEXT, attributedBody BLOB, is_from_me INTEGER,
                                  handle_id INTEGER, cache_has_attachments INTEGER, associated_message_type INTEGER,
                                  item_type INTEGER);
            CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
            CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT);
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            INSERT INTO handle VALUES (1, '+491701234567'), (2, '+15550000');
            INSERT INTO chat VALUES (1, '+491701234567'), (2, '+15550000');
        """)
    add(path, 1, "old message, before Milo")
    return path


def add(path, rowid, text, *, chat=1, from_me=1, handle=1, blob=None, reaction=0, files=0):
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO message VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                  (rowid, text, blob, from_me, handle, files, reaction))
        c.execute("INSERT INTO chat_message_join VALUES (?, ?)", (chat, rowid))


class Runner:
    def __init__(self, code=0, err=""):
        self.calls, self.code, self.err = [], code, err

    async def __call__(self, args):
        self.calls.append(list(args))
        return self.code, self.err


def channel(db, tmp_path, run=None):
    return IMessageChannel(HANDLE, db, tmp_path / "state" / "imessage.json", poll_s=0, run=run or Runner())


def test_typedstream_bodies_decode():
    assert decode_body(body("hello")) == "hello"
    assert decode_body(body("ü" * 100)) == "ü" * 100
    assert decode_body(None) == decode_body(b"garbage") == ""


def test_options_need_the_owners_own_handle():
    IMessageOptions(handle="me@icloud.com")
    with pytest.raises(ConfigError, match="handle"):
        IMessageOptions(handle="")
    assert handle_key("Me@iCloud.com") == "me@icloud.com" and handle_key(HANDLE) == KEY


def test_only_new_messages_of_the_owner_in_their_own_chat_count(db, tmp_path):
    ch = channel(db, tmp_path)

    async def go():
        await ch.start()
        add(db, 2, "send me the slides")
        add(db, 3, None, blob=body("and the notes"))
        add(db, 4, MARK + "On it.")  # Milo's own reply
        add(db, 5, "Loved “send me the slides”", reaction=2000)  # a tapback
        add(db, 6, "hi from a friend", chat=2, from_me=0, handle=2)
        add(db, 7, "", files=1)
        return await ch.receive()

    got = asyncio.run(go())
    assert [(m.text, m.chat, m.sender, m.attachments) for m in got] == [
        ("send me the slides", HANDLE, KEY, 0), ("and the notes", HANDLE, KEY, 0), ("", HANDLE, KEY, 1)]
    again = channel(db, tmp_path)
    asyncio.run(again.start())
    assert asyncio.run(again.receive()) == [], "the mark survives a restart"


def test_without_full_disk_access_milo_says_how_to_allow_it(tmp_path):
    ch = channel(tmp_path / "nope" / "chat.db", tmp_path)
    with pytest.raises(ChannelError) as e:
        asyncio.run(ch.start())
    assert str(e.value) == NO_ACCESS


def test_it_only_ever_writes_to_the_owner_and_marks_what_it_sends(db, tmp_path):
    run = Runner()
    ch = channel(db, tmp_path, run)
    asyncio.run(ch.send(HANDLE, "Your standup is at 10."))
    asyncio.run(ch.ask(HANDLE, "q1", "Send it?"))
    assert run.calls[0][-2:] == [MARK + "Your standup is at 10.", HANDLE]
    assert run.calls[1][-2] == MARK + "Send it?\n\nAnswer yes or no."
    assert "Your standup" not in run.calls[0][1], "the text is an argument, never part of the script"
    with pytest.raises(ChannelError, match="only writes to your own"):
        asyncio.run(ch.send("+15550000", "hi"))


def test_files_go_from_a_private_copy(db, tmp_path):
    run = Runner()
    ch = channel(db, tmp_path, run)
    asyncio.run(ch.send_file(HANDLE, "slides.key", b"deck", "today's slides"))
    copy = run.calls[-1][-2]
    assert open(copy, "rb").read() == b"deck" and os.stat(copy).st_mode & 0o777 == 0o600
    assert run.calls[0][-2] == MARK + "today's slides"


def test_a_refused_automation_permission_is_plain_words(db, tmp_path):
    ch = channel(db, tmp_path, Runner(1, "execution error: Not authorized to send Apple events (-1743)"))
    with pytest.raises(ChannelError, match="Automation"):
        asyncio.run(ch.send(HANDLE, "hi"))
