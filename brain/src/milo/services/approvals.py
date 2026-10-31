from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import uuid
from collections.abc import Callable, Mapping, Sequence

from milo.core.events import Confirm, ConfirmDone
from milo.core.logtext import private
from milo.core.ports import QuestionRelay, Relayed
from milo.core.registry import ConfigError
from milo.core.types import ActionLevel, Decision, Emotion, HandsError
from milo.core.words import say

from .permits import Permits, Scope
from .speaker import Speaker
from .transcript import Transcript, unrecorded
from .ui_state import UiState

log = logging.getLogger("milo.approvals")

DEFAULT_TIMEOUT_S = 0.0
"""0: a question at the Mac waits until it is answered (ADR 0031). A number: after that long no answer means no."""
REASK_S = 20.0
"""An unanswered question is said once more after this long."""
PARKED = ("The user hasn't answered yet; the question stays open for them. Don't do it another way: end your turn "
          "now and say in one short sentence that you're waiting for their answer. If they say yes, you'll be told "
          "to go on.")
"""What the worker hears when its question outlasts its turn (Parked)."""


class Parked(HandsError):
    """The question outlived the asker's turn: it stays open, and the asker hears the answer later (ADR 0031)."""

    def __init__(self):
        super().__init__(PARKED)

ALLOWED = ("yes", "always", "allowed")
"""Answers that let the action go ahead: "allowed" is work the user allowed before, so nobody was asked."""
REMOTE = "message"
"""`via` for answers from the owner's phone (a relay)."""

# What each kind of action gets unless config.toml says otherwise ([approvals.levels]). The line is whether it can
# be undone (ADR 0023).
DEFAULT_LEVELS: dict[str, ActionLevel] = {
    "read": ActionLevel.READ,  # reading, searching, listing
    "draft": ActionLevel.READ,  # a mail draft, nothing leaves the Mac
    "change": ActionLevel.CHANGE,  # a calendar entry, a note, a reminder: can be undone
    "trash": ActionLevel.CHANGE,  # to the Trash or Recently Deleted: can be undone, asks only in "Every step" mode
    "install": ActionLevel.CHANGE,  # a program from a package manager: asks unless the user named it
    "send": ActionLevel.ASK_FIRST,  # mail, messages
    "share": ActionLevel.ASK_FIRST,  # anything going to another person
    "delete": ActionLevel.ASK_FIRST,  # for good: emptying the Trash, places without one, uninstalling
    "discard": ActionLevel.ASK_FIRST,  # Don't Save: unsaved changes are gone
    "overwrite_file": ActionLevel.ASK_FIRST,  # a file on disk replaced by another
    "buy": ActionLevel.ASK_FIRST,
    "money": ActionLevel.ASK_FIRST,  # payments, transfers, withdrawals, selling
    "shortcut": ActionLevel.ASK_FIRST,  # a user's shortcut can do any of the above
    "password": ActionLevel.NEVER,
    "security": ActionLevel.NEVER,  # security and privacy settings
}
INSTALL = "install"
"""Installing a program (install_package). A `change`, but a helper's install also asks unless, in auto mode, the user's
own words for its task asked for an install and named that package (HelperQuestions.approve_install)."""
# Kinds config.toml can't make less strict.
ALWAYS_NEVER = ("password", "security")
MONEY_KINDS = ("buy", "money")
"""Always asked, and only a click on Yes answers (ADR 0023). config.toml may make them never, not less strict than
ask_first."""
UNDOABLE_KINDS = ("trash",)
"""Changes that remove something the user can get back. Like any change they don't ask, except in "Every step"
mode."""
_STRICTNESS = (ActionLevel.READ, ActionLevel.CHANGE, ActionLevel.ASK_FIRST, ActionLevel.NEVER)

_YES = ("yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead", "do it", "please do", "of course",
        "send it", "ja", "jawohl", "klar", "gerne", "genau", "mach das", "mach es", "mach")
_NO = ("no", "nope", "nah", "don't", "do not", "stop", "cancel", "not now", "wait", "nein", "nee", "nö",
       "lieber nicht", "nicht", "stopp", "abbrechen", "warte")
_MAX_ANSWER_WORDS = 6


class ActionPolicy:
    """Which ActionLevel each kind of action gets. Unknown kinds are ask_first.

    Older configs said `delete` for every delete. It now means deleting for good. `delete = "never"` without a
    `trash` line makes trash never too, so it still keeps Milo from deleting anything. `delete = "ask_first"` was the
    old default, which the template wrote out, so it says nothing about the Trash."""

    def __init__(self, levels: Mapping[str, object] | None = None):
        self._levels = dict(DEFAULT_LEVELS)
        levels = dict(levels or {})
        if "trash" not in levels and str(levels.get("delete")) == "never":
            levels["trash"] = levels["delete"]
        for kind, value in levels.items():
            if kind not in DEFAULT_LEVELS:
                raise ConfigError(f"[approvals.levels] unknown action {kind!r}; known: {', '.join(DEFAULT_LEVELS)}")
            try:
                level = ActionLevel(str(value))
            except ValueError:
                raise ConfigError(f"[approvals.levels] {kind} must be one of "
                                  f"{', '.join(lv.value for lv in ActionLevel)}") from None
            if kind in ALWAYS_NEVER and level is not ActionLevel.NEVER:
                raise ConfigError(f"[approvals.levels] {kind} is always never")
            if kind in MONEY_KINDS and _STRICTNESS.index(level) < _STRICTNESS.index(ActionLevel.ASK_FIRST):
                log.warning("[approvals.levels] %s = %s: buying and money always ask first", kind, level.value)
                level = ActionLevel.ASK_FIRST
            self._levels[kind] = level

    def level(self, kind: str) -> ActionLevel:
        return self._levels.get(kind, ActionLevel.ASK_FIRST)


def yes_or_no(text: str) -> bool | None:
    """A short spoken or typed answer as yes (True) or no (False). None if it is neither, or too long to be one."""
    words = re.sub(r"[^\w'’ ]+", " ", text.lower()).replace("’", "'").split()
    if not words or len(words) > _MAX_ANSWER_WORDS:
        return None
    phrase = " ".join(words)
    if any(phrase == c or phrase.startswith(c + " ") for c in _NO):
        return False
    if any(phrase == c or phrase.startswith(c + " ") for c in _YES):
        # "okay, wait, no" or "yes but don't send it" takes the yes back: not a plain answer.
        return None if any(f" {c} " in f" {phrase} " for c in _NO) else True
    return None



Parker = Callable[[asyncio.Future[str]], None]
POLL_S = 0.1


def _yes(answer: str) -> bool:
    if answer == "parked":
        raise Parked()
    return answer in ALLOWED


QUESTION_MAX = 240
"""The longest question the bubble shows whole."""
BUBBLE_LINES = 8
"""The lines the bubble shows (BubbleView's lineLimit)."""
LINE_CHARS = 32
"""Fewer characters than a bubble line holds, so the estimate of the lines a question needs errs high."""


def bubble_lines(text: str) -> int:
    """About how many lines `text` takes in the bubble, erring high: every kind of line break starts one
    (splitlines knows \r, \u2028 and the rest), long lines wrap, and wide characters (CJK, emoji) count twice."""
    return sum(max(1, -(-_width(line) // LINE_CHARS)) for line in text.splitlines() or [""])


def _width(line: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" or ord(c) > 0xFFFF else 1 for c in line)


def fit_bubble(question: str, detail: str, language: str = "") -> tuple[str, str]:
    """A question the bubble can show whole. A longer one, in characters or in lines, is cut where everyone can
    see it was cut, and the whole of it goes into the detail the Milo window shows: Yes must never sit under a
    hidden end."""
    if len(question) <= QUESTION_MAX and bubble_lines(question) <= BUBBLE_LINES:
        return question, detail
    whole = f"{question}\n\n{detail}" if detail else question
    see = say("approvals.see_window", language)
    room = QUESTION_MAX - len(see) - 1
    short = " ".join(question.split())[:room]
    while short and bubble_lines(short + "…" + see) > BUBBLE_LINES:
        short = short[:-LINE_CHARS]
    short = short.rsplit(" ", 1)[0].rstrip(",;: ") if " " in short else short
    return short + "…" + see, whole


class Approvals:
    """The confirm flow: before an ask_first action Milo asks a yes-or-no question and waits.

    The question shows in the bubble and the Milo window with Yes and No, and is spoken unless the user
    is busy talking (`quiet()`). It is answered by a click (`answer`), or by a short spoken or typed
    "yes"/"no" (`answer_text`, called by LiveTalk before it starts a turn) as long as the question is
    still the last thing Milo said: once the bubble shows anything else (a reply, a task result, a
    nudge), a bare "yes" could mean that, so only the buttons count. One question at a time; later ones wait their
    turn.

    An unanswered question stays open, in the bubble and on Today, and is said once more after `reask_s` (ADR 0031).
    A caller with a deadline of its own (a helper whose turn the harness ends) passes `wait_s` and `parked`: when
    the time is up the question stays open, the caller gets "parked" at once, and `parked` gets a future for the
    answer still to come; cancelling it takes the question away. `timeout_s` > 0 brings back
    the old rule (no answer in that time means no), and a question only the phone may answer waits as long as the
    relay says.

    `relays` pass questions on, like to the owner's phone when they are away (messages.py). A relayed
    question waits as long as the relay asks; one the relay takes `only` can't be answered at the Mac at
    all, since whoever sits there now isn't the user who asked for the work.

    A question about working in an app comes with a `Scope` (ADR 0022). If `permits` already allow that work
    (Allow earlier in the same task, or Allow always for the app) it isn't asked at all; otherwise it offers a
    third button, Allow always. Only a click on that button means always: a spoken or typed yes, or a yes from
    the phone, allows this time. Questions without a scope ask every time and never offer always.

    What can be undone (`undo`, the `trash` kind) asks only in "Every step" mode (ADR 0023). A question about money
    (`money`, the `buy` and `money` kinds) asks in every mode, never offers always, and only a click on Yes answers
    it: a spoken or typed yes, or a yes from the phone, doesn't count, and while the owner is away it isn't asked
    at all (the answer is no).
    """

    def __init__(self, ui: UiState, speaker: Speaker, policy: ActionPolicy | None = None, *,
                 timeout_s: float = DEFAULT_TIMEOUT_S, speak: bool = True, quiet: Callable[[], bool] = lambda: False,
                 transcript: Transcript | None = None, permits: Permits | None = None,
                 language: Callable[[], str] = lambda: "", reask_s: float = REASK_S):
        self._ui = ui
        self._language = language
        """The code of the language the user last spoke in: Milo's own lines here follow it (German or English)."""
        self._speaker = speaker
        self.policy = policy or ActionPolicy()
        self._timeout_s = timeout_s
        self._reask_s = reask_s
        self._expired: set[asyncio.Task] = set()
        self._speak = speak
        self._quiet = quiet
        self._transcript = transcript or unrecorded()
        self._one_at_a_time = asyncio.Lock()
        self.permits = permits or Permits()
        self._pending: tuple[str, str, asyncio.Future[str], bool] | None = None
        """id, question, the answer to come ("yes", "no", "always" or a choice's id), whether Allow always was
        offered."""
        self._money = False
        """The waiting question is about money: only a click on Yes answers it."""
        self._choices: tuple[tuple[str, str], ...] = ()
        """The waiting question's own buttons, (id, label) each, shown instead of Yes and No."""
        self._remote_only = False
        self.relays: list[QuestionRelay] = []

    @property
    def pending(self) -> bool:
        return self._pending is not None

    @property
    def money_pending(self) -> bool:
        """A question about money waits: nothing may act on the screen until it is answered, so no click can land
        on its Yes button but the user's."""
        return self._pending is not None and self._money

    def asks(self, kind: str, *, careful: bool = False) -> bool:
        """Whether approve() asks the user about `kind`: when it is ask_first, a change for a careful helper (one
        asked for in a conversation that read outside text, like the screen), or a change that removes something
        (trash) in "Every step" mode."""
        level = self.policy.level(kind)
        return level is ActionLevel.ASK_FIRST or (level is ActionLevel.CHANGE and (
            careful or (kind in UNDOABLE_KINDS and self.asks_undoable())))

    def asks_undoable(self) -> bool:
        """Whether what can be undone asks at all: only in "Every step" mode (ADR 0023), unless config.toml makes
        `trash` stricter than a change."""
        return self.permits.ask == "step" or self.policy.level("trash") in (ActionLevel.ASK_FIRST, ActionLevel.NEVER)

    async def approve(self, kind: str, summary: str, *, careful: bool = False, scope: Scope | None = None,
                      wait_s: float | None = None, parked: Parker | None = None) -> Decision:
        """Apply the level for `kind`, asking `summary` if asks() says so. `scope`: the app the action works in,
        which only a careful helper's `change` uses: an ask_first kind (send, delete, buy...) asks every time.
        `wait_s` and `parked`: see the class docstring; the answer is then "parked"."""
        level = self.policy.level(kind)
        if level is ActionLevel.NEVER:
            log.info("refused a %s action", kind)
            return Decision(False, level, "refused")
        if not self.asks(kind, careful=careful):
            return Decision(True, level, "auto")
        answer = await self._ask(summary, scope=scope if level is ActionLevel.CHANGE else None,
                                 money=kind in MONEY_KINDS, wait_s=wait_s, parked=parked)
        return Decision(answer in ALLOWED, level, answer)

    async def confirm(self, summary: str, *, detail: str = "", speak: bool = True, scope: Scope | None = None,
                      undo: bool = False, money: bool = False, wait_s: float | None = None,
                      parked: Parker | None = None) -> bool:
        """Confirmer: ask, unless `scope` is work the user already allowed. `detail` shows under the question in
        the Milo window, e.g. the whole task. speak=False only shows it, for a question asked while the user is in
        a call. `undo`: the action can be undone, so only "Every step" mode asks. `money`: it buys or pays, so it
        asks every time and only a click on Yes counts. `wait_s` and `parked`: see the class docstring; a question
        that parks raises Parked."""
        if undo and not money:
            # Screen actions follow the classifier, but a stricter `trash` level in config.toml still counts.
            level = self.policy.level("trash")
            if level is ActionLevel.NEVER:
                log.info("refused moving something to the Trash ([approvals.levels] trash)")
                return False
            if level is ActionLevel.ASK_FIRST:
                return _yes(await self._ask(summary, detail, speak, wait_s=wait_s, parked=parked))
            if not self.asks_undoable():
                log.info("can be undone, so not asking: %s", private(summary))
                return True
        return _yes(await self._ask(summary, detail, speak, scope=None if money else scope, money=money,
                                    wait_s=wait_s, parked=parked))

    async def choose(self, question: str, choices: Sequence[tuple[str, str]], *, speak: bool = True) -> str:
        """Ask with buttons of its own, (id, label) each, instead of Yes and No. Returns the id clicked; "yes" or
        "no" for a spoken or typed answer, a choice-less button or the phone; "timeout" if nobody answered. It has
        no scope and isn't about money, so no Allow always: an "always" among the choices is the asker's own."""
        return await self._ask(question, "", speak, choices=tuple(choices))

    def answer(self, id: str, yes: bool, *, via: str = "button", always: bool = False, choice: str = "") -> bool:
        """Answer the waiting question `id`. `always`: the Allow always button, which counts only where it was
        offered. `choice`: one of the question's own buttons, if it has them; it wins over `yes` and `always`.
        False if it isn't the one waiting (already answered, timed out)."""
        if self._pending is None or self._pending[0] != id or self._pending[2].done():
            return False
        if self._remote_only and via != REMOTE:
            log.info("an answer at the Mac to a question only the phone may answer")
            return False
        if self._money and yes and via != "button":
            log.info("a %s yes to a question about money, which only a click answers", via)
            return False
        labels = dict(self._choices)
        if choice in labels:
            self._transcript.user(labels[choice], via)
            self._pending[2].set_result(choice)
            return True
        always = yes and always and via == "button" and self._pending[3]
        self._transcript.user("Allow always" if always else "Yes" if yes else "No", via)
        self._pending[2].set_result("always" if always else "yes" if yes else "no")
        return True

    def answer_text(self, text: str, *, via: str = "voice") -> bool:
        """Treat a turn as the answer if the waiting question is the last thing Milo said and the turn is
        a plain yes or no."""
        if self._pending is None or self._remote_only or not self._still_showing(self._pending[1]):
            return False
        yes = yes_or_no(text)
        if yes is None:
            return False
        if yes and self._money:
            # Taken as the answer so it isn't a turn of its own, but it doesn't say yes: the button has to.
            money_yes = say("approvals.money_yes", self._language())
            self._transcript.say(money_yes, Emotion.NEUTRAL)
            self._speaker.say(money_yes, Emotion.NEUTRAL, speak=self._speak and via == "voice")
            return True
        return self.answer(self._pending[0], yes, via=via)

    def cancel(self) -> bool:
        """The user pressed Stop: the waiting question, wherever it was asked, is answered no."""
        if self._pending is None or self._pending[2].done():
            return False
        self._transcript.user("Stop", "button")
        self._pending[2].set_result("no")
        return True

    def _still_showing(self, question: str) -> bool:
        """The bubble shows the question, or the part of it spoken so far."""
        shown = self._ui.bubble.strip()
        return bool(shown) and question.startswith(shown)

    async def _ask(self, question: str, detail: str = "", speak: bool = True, *, scope: Scope | None = None,
                   money: bool = False, choices: tuple[tuple[str, str], ...] = (), wait_s: float | None = None,
                   parked: Parker | None = None) -> str:
        """Returns "yes", "always", "no", "timeout", "allowed" when `scope` was allowed before, "parked" (see the
        class docstring), or the id of one of `choices`. A `money` question has no scope, and while the owner is away
        it is "no" without asking. A question with `choices` shows only those buttons, so it takes no scope (no Allow
        always) and no money."""
        if choices:
            scope, money = None, False
        if self._timeout_s > 0:
            wait_s, parked = None, None  # the old rule: no answer in `timeout_s` means no
        flow = asyncio.ensure_future(self._question(question, detail, speak, scope=scope, money=money,
                                                    choices=choices))
        try:
            await asyncio.wait({flow}, timeout=wait_s)
        except asyncio.CancelledError:
            flow.cancel()
            raise
        if flow.done():
            return flow.result()
        if parked is None:
            self._expired.add(flow)
            flow.cancel()
            await asyncio.wait({flow})
            self._expired.discard(flow)
            return "timeout"
        log.info("the asker can't wait longer; the question stays open: %s", private(question))
        answer: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        flow.add_done_callback(lambda f: answer.done() or answer.set_result(
            "no" if f.cancelled() or f.exception() is not None else f.result()))
        answer.add_done_callback(lambda a: flow.cancel() if a.cancelled() else None)
        parked(answer)
        return "parked"

    async def _question(self, question: str, detail: str, speak: bool, *, scope: Scope | None, money: bool,
                        choices: tuple[tuple[str, str], ...]) -> str:
        """Show and say one question once it is its turn, and wait for its answer."""
        async with self._one_at_a_time:
            # Checked in the lock: the yes to a question waiting before this one may cover it.
            covered = self.permits.covers(scope) if scope is not None else ""
            if covered:
                log.info("allowed without asking (%s): %s", covered, private(question))
                return "allowed"
            id = uuid.uuid4().hex[:12]
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            if money:
                scope = None
                relayed = self._relay(id, question, detail, money=True)
                if any(r.only for r in relayed):
                    log.info("not asking about money while the owner is away: %s", private(question))
                    self._transcript.say(f"I stopped before this, since it involves money and you're away: "
                                         f"{question}", Emotion.NEUTRAL)
                    return "no"
            self._pending = (id, question, future, scope is not None)
            self._money = money
            self._choices = choices
            log.info("asking before an action%s: %s", " (money)" if money else "", private(question))
            if not money:
                relayed = self._relay(id, question, detail)
            self._remote_only = any(r.only for r in relayed)
            waits = [r.wait_s for r in relayed]
            timeout_s = (max(waits) if self._remote_only and waits else
                         max([self._timeout_s, *waits]) if self._timeout_s > 0 else None)
            question, detail = fit_bubble(question, detail, self._language())
            text = f"{question}\n\n{detail}" if detail else question
            if self._remote_only:
                # The user is away: the Mac only shows that a question went to the phone, without buttons.
                self._transcript.say(f"Asked on your phone: {text}", Emotion.THINKING)
                self._speaker.say(f"Asked on your phone: {question}", Emotion.THINKING, speak=False)
            else:
                self._ui.emit(Confirm(id, question, always=scope is not None, money=money,
                                      choices=tuple({"id": c, "label": label} for c, label in choices)))
                self._transcript.say(text, Emotion.THINKING)
                self._speaker.say(question, Emotion.THINKING, speak=speak and self._speak and not self._quiet())
            answer = "no"
            try:
                if not self._remote_only and speak and self._speak:
                    await self._ask_again(future, question, timeout_s)
                answer = await asyncio.wait_for(future, timeout_s)
            except TimeoutError:
                answer = "timeout"
                self._transcript.say(say("approvals.no_answer", self._language()), Emotion.NEUTRAL)
            except asyncio.CancelledError:
                if asyncio.current_task() not in self._expired:
                    raise
                self._expired.discard(asyncio.current_task())
                answer = "timeout"
                self._transcript.say(say("approvals.no_answer", self._language()), Emotion.NEUTRAL)
            finally:
                self._pending = None
                self._money = False
                self._choices = ()
                if not self._remote_only:
                    self._ui.emit(ConfirmDone(id, answer))
                self._remote_only = False
                for relay in self.relays:
                    try:
                        relay.closed(id, "yes" if answer == "always" and not choices else answer)
                    except Exception:
                        log.exception("a question relay failed")
            log.info("the answer was %s", answer)
            if scope is not None and answer in ("yes", "always"):
                self.permits.allowed(scope, always=answer == "always")
            return answer

    async def _ask_again(self, future: asyncio.Future[str], question: str, timeout_s: float | None) -> None:
        """Say an unanswered question once more after `reask_s`, once the user isn't talking and Milo is quiet."""
        if self._reask_s <= 0 or (timeout_s is not None and timeout_s <= self._reask_s):
            return
        await asyncio.wait({future}, timeout=self._reask_s)
        while not future.done() and (self._quiet() or self._speaker.active):
            await asyncio.wait({future}, timeout=POLL_S)
        if not future.done():
            log.info("no answer yet; asking once more")
            self._speaker.say(question, Emotion.THINKING)

    def _relay(self, id: str, question: str, detail: str, *, money: bool = False) -> list[Relayed]:
        relayed = []
        for relay in self.relays:
            try:
                taken = relay.asked(id, question, detail, money=True) if money else relay.asked(id, question, detail)
            except Exception:
                log.exception("a question relay failed")
                continue
            if taken is not None:
                relayed.append(taken)
        return relayed
