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

from .quick_words import language
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
want it in, with its line breaks; no greeting to Milo, no notes around it. Say nothing else: Milo says one short \
line himself once it is in.
- This comes before the rules above: use <write>, not a <task> or a <draft>. Use <draft> only when the user says \
to put it in Mail as a draft.
- To write about what is on the screen ("answer this email", "reply to this message"), write only <look/> first, \
with no words. In your reply to the screen, write the <write> tag.
- One <write> per reply. When the user wants it changed ("shorter", "more polite"), write all of it again.
- "Undo that" right after one is <undo/>.
"""

LINES: dict[str, dict[str, str]] = {
    "pasted": {"en": "It's in {app}, have a look.", "de": "Steht in {app}, schau mal drüber."},
    "pasted_here": {"en": "It's in, have a look.", "de": "Steht drin, schau mal drüber."},
    "here": {"en": "Here it is, ready to copy.", "de": "Hier ist es, zum Kopieren."},
    "moved": {"en": "You'd moved on, so I didn't paste it. It's in my window to copy.",
              "de": "Du warst schon woanders, also hab ich's nicht eingefügt. Es liegt zum Kopieren in meinem Fenster."},
    "no_field": {"en": "I didn't find a text field there, so it's in my window to copy.",
                 "de": "Ich hab dort kein Textfeld gefunden. Es liegt zum Kopieren in meinem Fenster."},
    "terminal": {"en": "I don't paste into a terminal, so it's in my window to copy.",
                 "de": "In ein Terminal füge ich nichts ein. Es liegt zum Kopieren in meinem Fenster."},
    "secure": {"en": "That's a password field, so I didn't paste. It's in my window to copy.",
               "de": "Das ist ein Passwortfeld, da füge ich nichts ein. Es liegt zum Kopieren in meinem Fenster."},
    "outside": {"en": "This comes from something I read, so look it over first. It's in my window to copy.",
                "de": "Das stammt aus etwas, das ich gelesen habe, schau es erst durch. Es liegt zum Kopieren in "
                      "meinem Fenster."},
    "failed": {"en": "I couldn't paste it, so it's in my window to copy.",
               "de": "Ich konnte es nicht einfügen. Es liegt zum Kopieren in meinem Fenster."},
}
"""The line after a <write>, by what happened: "pasted", or why it is only in the window (the app's `why`)."""

# The user's own words ask for something written: then outside text read before can't be what started it. The writing
# verb has to lead the request ("answer this email", "okay, write Anna back", "can you reply to Tom"), so a question or
# a sentence that only mentions a reply ("can you tell me what the reply says?") never counts.
_EN = r"writ(?:e|es)|answer|repl(?:y|ies)|respond|draft|compose|summari[sz]e|rephrase|reword|rewrite|translate|formulate"
_DE = r"schreib\w*|antworte\w*|beantworte\w*|formulier\w*|übersetz\w*|entwirf|verfass\w*|zusammenfass\w*"
_LEAD = (r"^\s*(?:(?:yes|yeah|ok|okay|alright|please|so|and|now|then|ja|bitte|also|und|jetzt|dann|okay)\b[\s,.!]*)*"
         r"(?:please\s+|bitte\s+)?")
_START = re.compile(_LEAD + rf"(?:{_EN}|{_DE}|fass\w*\b.{{0,40}}\bzusammen|(?:make|mach)\w*\b.{{0,20}}\b(?:shorter|"
                    r"longer|more polite|nicer|friendlier|kürzer|länger|höflicher|netter|freundlicher))\b", re.IGNORECASE)
_ASK = re.compile(_LEAD + rf"(?:(?:can|could|would|will) you\s+(?:please\s+)?(?:{_EN})\b|"
                  rf"(?:kannst|könntest|würdest) du\b.{{0,60}}\b(?:{_DE})\W*$)", re.IGNORECASE)
_NOUN = re.compile(r"^\s*(?:a|an|eine?n?)\s+(?:\w+\s+){0,2}(?:summary|reply|answer|e-?mail|mail|message|post|"
                   r"zusammenfassung|antwort|nachricht)\s+(?:for|to|saying|für|an)\b(?![^?]*\?\s*$)", re.IGNORECASE)

_HIDDEN = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")


def asks_to_write(text: str) -> bool:
    """Whether the user's own words ask for text to be written: "write Anna", "answer this email", "make it shorter",
    "can you reply to Tom", "a short summary for Slack", "schreib ihr", "fass das zusammen". A question about the text
    or a sentence that only names one ("what does the reply say?", "can you tell me what the reply says?", "an email
    from my bank, is it legit?", "was hat er geantwortet?") never is, so outside text can't ride on it."""
    return any(pattern.search(text) for pattern in (_START, _ASK, _NOUN))


def clean(text: str) -> str:
    """The text as it may be pasted: line breaks and tabs kept, every other control character and the invisible ones
    (bidi overrides, zero-width, tag characters) out, so no word can hide from the user. Cut at MAX_CHARS."""
    text = _HIDDEN.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "".join(c for c in text if c in "\n\t" or unicodedata.category(c) != "Cc")
    return text[:MAX_CHARS]


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
    templates = LINES.get(key) or LINES["failed"]
    return templates.get(lang, templates["en"]).format(**values)


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

    def start(self, texts: Sequence[str], *, outside: bool, request: str, via: str = "voice") -> None:
        """Hand the reply's <write> texts to the app now, while the reply still streams. `outside`: the conversation
        read outside text, or the message being answered carried it. `request`: the user's own words this turn.
        A reply by message carries the text itself (LiveTalk), so nothing is pasted from the phone."""
        if via == "message":
            return
        turn = asyncio.current_task()
        lang = language(self._language())
        own = asks_to_write(request)
        for text in texts:
            text = clean(text)
            if not text.strip():
                continue
            first = self._pasted.get(turn, 0) == 0
            self._pasted[turn] = self._pasted.get(turn, 0) + 1
            # One text per reply goes in; after outside text only when the user asked for writing in this turn.
            held = "outside" if outside and not own else "" if first else "here"
            task = asyncio.create_task(self._write(text, held=held, turn=turn, lang=lang))
            self._running.add(task)
            task.add_done_callback(self._running.discard)
        if turn is not None:
            turn.add_done_callback(lambda t: self._pasted.pop(t, None))

    async def idle(self) -> None:
        """Wait until every write is done and said. For tests."""
        while self._running:
            await asyncio.wait(set(self._running))

    async def _write(self, text: str, *, held: str, turn: asyncio.Task | None, lang: str) -> None:
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
