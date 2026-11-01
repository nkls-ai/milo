"""Text Milo writes for where the user is, pasted into the field they were in (ADR 0033).

"Write Anna that I'm ten minutes late", "answer this politely", "a short summary of what we discussed for Slack": the
live model writes the text in a `<write>` tag, which is never spoken. The moment the tag closes this service asks the
app to paste it (`text.write`) the way dictation pastes, into the field that had the focus when the talk key went
down. The app checks that field is still the one in front, a text field, not a password field and not a terminal,
and says whether it pasted. Then Milo says one templated line ("It's in Mail, have a look."), the window gets the
text with a Copy button, a card shows its first words, and "undo that" takes exactly that text back out (`text.unwrite`).

What may be pasted. Pasting isn't sending: the user reads it in their own field before anything leaves. But text the
model wrote after reading outside text (the screen, a task's result, another person's line in <today>) may carry
words someone else put there. So after outside text Milo pastes only when the user's own words in this turn asked
for the writing ("answer this email"); otherwise the text waits in the window to be copied. Hidden characters
(controls, bidi overrides, zero-width and tag characters) never go along: they could hide words from the user.
At most one text per reply is pasted. The brain decides what may go; the app decides where it may land. The paste
itself is the app's, so the brain stays platform-neutral (ADR 0027).
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from milo.core.events import ActionDone
from milo.core.logtext import private
from milo.core.ports import EventSink
from milo.core.types import Emotion
from milo.core.words import has, language, say

from .speaker import Speaker
from .transcript import Transcript, unrecorded

if TYPE_CHECKING:
    from .undo import Undo

log = logging.getLogger("milo.write")

AppCall = Callable[[str, dict], Awaitable[Any]]

MAX_CHARS = 20_000
TITLE_WORDS = 6
TITLE_CHARS = 48
WAIT_FOR_QUIET_S = 15.0
POLL_S = 0.05

RULES = """\
## Writing text for the user

- <write>the text</write> when the user wants something written for where they are: a mail, a message, an \
answer, a summary, a post ("write Anna that I'm late", "answer this politely", "a short summary for Slack"). \
Milo pastes it where their cursor is. Write only the text itself, in the user's voice and in the language they \
want it in, with its line breaks; no greeting to Milo, no notes around it. The reply is the tag alone, with no \
words before or after it ("Done", "Written in"): only the app knows whether it went in, and Milo says that himself.
- This comes before the rules above: use <write>, not a <task> or a <draft>. Use <draft> only when the user says \
to put it in Mail as a draft.
- To write about what is on the screen ("answer this email", "reply to this message"), write only <look/> first, \
with no words. In your reply to the screen, write the <write> tag.
- One <write> per reply. When the user wants it changed ("shorter", "more polite"), write all of it again.
- <copy>the text</copy> puts it on the user's clipboard. Use it whenever the user asks for something they will \
paste somewhere: a link or web address, an email address, a phone number, an address, a code, a command, a short \
snippet ("what's the link to the Milo repo?", "give me Anna's email", "the tracking number?"). Say one short line \
like "The link's on your clipboard." Never read a link or a long code out loud; a short number you may say too. \
Only what the user asked for, never anything else, and only text you are sure of.
- "Undo that" right after one is <undo/>.
"""

_HIDDEN = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")


def clean(text: str) -> str:
    """The text as it may be pasted: line breaks and tabs kept, every other control character and the invisible ones
    (bidi overrides, zero-width, tag characters) out, so no word can hide from the user. Cut at MAX_CHARS."""
    text = _HIDDEN.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c) != "Cc")
    return text[:MAX_CHARS]


# The shapes a value to paste has, none of which a shell would run: no $, backticks, braces, quotes or spaces in a
# link, and an & in one only before a "name=" (an assignment to a shell). An address is free text that can't be told
# from a command, so after outside text it waits in the window.
_LINK_CHARS = r"[A-Za-z0-9\-._~:/?#@=+,%]"
_VALUES = tuple(re.compile(p) for p in (
    rf"https?://{_LINK_CHARS}+(?:&[A-Za-z0-9._-]+={_LINK_CHARS}*)*",  # a link
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",  # an email address
    r"\+?\d[\d ()./-]{4,24}",  # a phone number
    r"[A-Za-z0-9][A-Za-z0-9._-]{1,63}",  # a code, a tracking number, a Wi-Fi password: one word
))
_COMMAND = re.compile(r"^\s*(?:sudo|curl|wget|sh|bash|zsh|fish|powershell|pwsh|iex|python3?|perl|ruby|node|npx|"
                      r"eval|exec|rm|chmod|chown|xattr|open|defaults|launchctl|killall|diskutil)\b", re.IGNORECASE)


def plain_value(text: str) -> bool:
    """Whether a text is a value to paste, not something to run: one line that is a link, an email address, a phone
    number or a one-word code. After outside text only those go on the clipboard by themselves: anything
    else an email or web page slipped in ("paste this in Terminal") waits in the window, where the user sees all of
    it before copying it."""
    text = text.strip()
    return not _COMMAND.match(text) and any(shape.fullmatch(text) for shape in _VALUES)


def first_words(text: str) -> str:
    """The card's title: the start of the first line with words."""
    line = next((line for line in text.splitlines() if line.strip()), "")
    words = line.split()
    short = " ".join(words[:TITLE_WORDS])
    if len(short) > TITLE_CHARS:
        short = short[:TITLE_CHARS - 1].rstrip() + "…"
    elif len(words) > TITLE_WORDS:
        short += "…"
    return short


def line(key: str, lang: str, **values: str) -> str:
    """The line for `key` (core/words/writing.py); an unknown reason from the app says it failed."""
    return say(f"writing.{key}" if has(f"writing.{key}") else "writing.failed", lang, **values)


class Writer:
    """See the module docstring. `app` sends one op to the app and returns its result (AppBridge.call); it raises with
    plain words when the app can't. `quiet` says the user is talking, so the line waits (up to `wait_s`) or only
    shows. `undo` gets a record for each paste, and its `reverse` learns the `write.remove` step."""

    def __init__(self, app: AppCall, ui: EventSink, speaker: Speaker, *, transcript: Transcript | None = None,
                 undo: Undo | None = None, quiet: Callable[[], bool] = lambda: False,
                 language: Callable[[], str] = lambda: "", wait_s: float = WAIT_FOR_QUIET_S, poll_s: float = POLL_S):
        self._app = app
        self._ui = ui
        self._speaker = speaker
        self._transcript = transcript or unrecorded()
        self._undo = undo
        self._quiet = quiet
        self._language = language
        self._wait_s = wait_s
        self._poll_s = poll_s
        self._running: set[asyncio.Task] = set()
        self._pasted: dict[asyncio.Task, int] = {}
        if undo is not None:
            others = undo.reverse  # QuickActions' steps; a write's go here

            async def reverse(step: dict) -> bool:
                if step.get("op") == "write.remove":
                    return await self._unwrite(step)
                if others is None:
                    raise ValueError(f"I don't know how to undo {step.get('op')}")
                return await others(step)

            undo.reverse = reverse

    def rules(self) -> str:
        return RULES

    def start(self, texts: Sequence[str], *, outside: bool, own: Callable[[], Awaitable[bool]],
              via: str = "voice") -> None:
        """Hand the reply's <write> texts to the app now, while the reply still streams. `outside`: the conversation
        read outside text, or the message being answered carried it. `own`: whether the user's own words this turn
        asked for writing (TagPolicy.own_write), awaited only after outside text.
        A reply by message carries the text itself (LiveTalk), so nothing is pasted from the phone."""
        if via == "message":
            return
        turn = asyncio.current_task()
        lang = language(self._language())
        for text in texts:
            text = clean(text)
            if not text.strip():
                continue
            first = self._pasted.get(turn, 0) == 0
            self._pasted[turn] = self._pasted.get(turn, 0) + 1
            # One text per reply goes in; after outside text only when the user asked for writing in this turn.
            task = asyncio.create_task(self._write(text, held="" if first else "here", turn=turn, lang=lang,
                                                   own=own if outside else None))
            self._running.add(task)
            task.add_done_callback(self._running.discard)
        if turn is not None:
            turn.add_done_callback(lambda t: self._pasted.pop(t, None))

    def copy(self, texts: Sequence[str], *, outside: bool, via: str = "voice", in_turn: bool = True) -> None:
        """Put each <copy> text on the clipboard now (`text.copy`), while the reply still streams; the window keeps it
        to copy again and a card shows it. The reply says it's there. From the phone the text goes in the answer.
        `outside`: the conversation or the helper read outside text, so only a plain value goes on the clipboard by
        itself (plain_value); anything else waits in the window to copy.
        `in_turn`: called from a reply, whose card the copy's card follows; a helper's result has none to wait for."""
        if via == "message":
            return
        turn = asyncio.current_task() if in_turn else None
        lang = language(self._language())
        for text in texts:
            text = clean(text)
            if text.strip():
                hold = outside and not plain_value(text)
                task = asyncio.create_task(self._copy(text, turn=turn, lang=lang, hold=hold))
                self._running.add(task)
                task.add_done_callback(self._running.discard)

    async def _copy(self, text: str, *, turn: asyncio.Task | None, lang: str, hold: bool) -> None:
        copied = False
        if hold:
            log.info("kept %d characters in the window to copy: not a plain value, after outside text", len(text))
        else:
            try:
                await self._app("text.copy", {"text": text})
                copied = True
            except Exception as e:  # no app connected, or it couldn't: the text still waits in the window
                log.info("couldn't put a text on the clipboard: %s", e)
            log.info("copied %d characters%s", len(text), "" if copied else ": failed, kept in the window")
        if turn is not None and turn is not asyncio.current_task():
            await asyncio.wait({turn})
        self._transcript.written(text)
        self._ui.emit(ActionDone("copied" if copied else "written", first_words(text), "", "", "", "", lang))
        if not copied:
            await self._say(line("here" if hold else "copy_failed", lang))

    async def idle(self) -> None:
        """Wait until every write is done and said. For tests."""
        while self._running:
            await asyncio.wait(set(self._running))

    async def _write(self, text: str, *, held: str, turn: asyncio.Task | None, lang: str,
                     own: Callable[[], Awaitable[bool]] | None = None) -> None:
        if own is not None and not await own():
            held = "outside"
        try:
            result = await self._app("text.write", {"text": text, "paste": not held})
            result = result if isinstance(result, dict) else {}
        except Exception as e:  # no app connected, or it couldn't: the text still waits in the window
            log.info("couldn't hand a written text to the app: %s", e)
            result = {"pasted": False, "why": "failed"}
        pasted = bool(result.get("pasted")) and not held
        app = str(result.get("app") or "")
        title = first_words(text)
        why = held or str(result.get("why") or "failed")
        said = (line("pasted", lang, app=app) if app else line("pasted_here", lang)) if pasted else line(why, lang)
        log.info("wrote %d characters, %s", len(text), f"pasted into {app or 'the field'}" if pasted
                 else f"kept in the window ({why})")
        undo = self._record(title, said, text, str(result.get("field") or ""), app) if pasted else ""
        if turn is not None and turn is not asyncio.current_task():
            await asyncio.wait({turn})  # the line and the window's copy come after the reply
        self._transcript.written(text)
        self._ui.emit(ActionDone("written", title, "", "", app if pasted else "", undo, lang))
        await self._say(said)

    def _record(self, title: str, said: str, text: str, field: str, app: str) -> str:
        if self._undo is None:
            return ""
        task = "w-" + uuid.uuid4().hex[:12]
        try:
            self._undo.done(task, title=title, said=said,
                            reverse=[{"op": "write.remove", "field": field, "text": text, "app": app}])
        except Exception:
            log.exception("could not keep an undo record for a written text")
            return ""
        return task

    async def _unwrite(self, step: dict) -> bool:
        """Take the pasted text back out: the app selects it and deletes it, only if the field still ends with it
        where it went in. Otherwise its words (the app's own Undo key) come back as the reason."""
        try:
            result = await self._app("text.unwrite", {"field": step.get("field", ""), "text": step.get("text", "")})
        except Exception as e:
            raise ValueError(str(e)) from None
        if isinstance(result, dict) and result.get("removed") is False:
            raise ValueError(str(result.get("why") or "the text there changed since"))
        log.info("took a written text back out, %s", private(step.get("text", "")))
        return True

    async def _say(self, text: str) -> None:
        """Once Milo is done speaking and the user isn't talking; after `wait_s` it only shows."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._wait_s
        speak = True
        while self._quiet() or self._speaker.active:
            if loop.time() >= deadline:
                speak = False
                break
            await asyncio.sleep(self._poll_s)
        self._transcript.say(text, Emotion.HAPPY)
        await self._speaker.say(text, Emotion.HAPPY, speak=speak)
