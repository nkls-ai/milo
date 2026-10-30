from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Callable, Mapping

from milo.core.events import Confirm, ConfirmDone
from milo.core.logtext import private
from milo.core.registry import ConfigError
from milo.core.types import ActionLevel, Decision, Emotion

from .speaker import Speaker
from .transcript import Transcript, unrecorded
from .ui_state import UiState

log = logging.getLogger("milo.approvals")

DEFAULT_TIMEOUT_S = 60.0
NO_ANSWER = "No answer, so I left it."

# What each kind of action gets unless config.toml says otherwise ([approvals.levels]).
DEFAULT_LEVELS: dict[str, ActionLevel] = {
    "read": ActionLevel.READ,  # reading, searching, listing
    "draft": ActionLevel.READ,  # a mail draft, nothing leaves the Mac
    "change": ActionLevel.CHANGE,  # a calendar entry, a note, a reminder: can be undone
    "send": ActionLevel.ASK_FIRST,  # mail, messages
    "share": ActionLevel.ASK_FIRST,  # anything going to another person
    "delete": ActionLevel.ASK_FIRST,
    "buy": ActionLevel.ASK_FIRST,
    "shortcut": ActionLevel.ASK_FIRST,  # a user's shortcut can do any of the above
    "password": ActionLevel.NEVER,
    "money": ActionLevel.NEVER,  # transfers, payments beyond a purchase the user confirmed
    "security": ActionLevel.NEVER,  # security and privacy settings
}
# Kinds config.toml can't make less strict.
ALWAYS_NEVER = ("password", "money", "security")

_YES = ("yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead", "do it", "please do", "of course",
        "send it", "ja", "jawohl", "klar", "gerne", "genau", "mach das", "mach es", "mach")
_NO = ("no", "nope", "nah", "don't", "do not", "stop", "cancel", "not now", "wait", "nein", "nee", "nö",
       "lieber nicht", "nicht", "stopp", "abbrechen", "warte")
_MAX_ANSWER_WORDS = 6


class ActionPolicy:
    """Which ActionLevel each kind of action gets. Unknown kinds are ask_first."""

    def __init__(self, levels: Mapping[str, object] | None = None):
        self._levels = dict(DEFAULT_LEVELS)
        for kind, value in (levels or {}).items():
            if kind not in DEFAULT_LEVELS:
                raise ConfigError(f"[approvals.levels] unknown action {kind!r}; known: {', '.join(DEFAULT_LEVELS)}")
            try:
                level = ActionLevel(str(value))
            except ValueError:
                raise ConfigError(f"[approvals.levels] {kind} must be one of "
                                  f"{', '.join(lv.value for lv in ActionLevel)}") from None
            if kind in ALWAYS_NEVER and level is not ActionLevel.NEVER:
                raise ConfigError(f"[approvals.levels] {kind} is always never")
            self._levels[kind] = level

    def level(self, kind: str) -> ActionLevel:
        return self._levels.get(kind, ActionLevel.ASK_FIRST)


def yes_or_no(text: str) -> bool | None:
    """A short spoken or typed answer as yes (True) or no (False). None if it is neither, or too long to be one."""
    words = re.sub(r"[^\w'’ ]+", " ", text.lower()).replace("’", "'").split()
    if not words or len(words) > _MAX_ANSWER_WORDS:
        return None
    phrase = " ".join(words)
    for answer, choices in ((False, _NO), (True, _YES)):
        if any(phrase == c or phrase.startswith(c + " ") for c in choices):
            return answer
    return None


class Approvals:
    """The confirm flow: before an ask_first action Milo asks a yes-or-no question and waits.

    The question shows in the bubble and the Milo window with Yes and No, and is spoken unless the user
    is busy talking (`quiet()`). It is answered by a click (`answer`), or by a short spoken or typed
    "yes"/"no" (`answer_text`, called by LiveTalk before it starts a turn) as long as the question is
    still the last thing Milo said: once the bubble shows anything else (a reply, a task result, a
    nudge), a bare "yes" could mean that, so only the buttons count. No answer within `timeout_s` means no. One question at a time;
    later ones wait their turn.
    """

    def __init__(self, ui: UiState, speaker: Speaker, policy: ActionPolicy | None = None, *,
                 timeout_s: float = DEFAULT_TIMEOUT_S, speak: bool = True, quiet: Callable[[], bool] = lambda: False,
                 transcript: Transcript | None = None):
        self._ui = ui
        self._speaker = speaker
        self.policy = policy or ActionPolicy()
        self._timeout_s = timeout_s
        self._speak = speak
        self._quiet = quiet
        self._transcript = transcript or unrecorded()
        self._one_at_a_time = asyncio.Lock()
        self._pending: tuple[str, str, asyncio.Future[bool]] | None = None
        self.careful = False
        """The running task came from a conversation that read outside text (the screen): changes ask too."""

    @property
    def pending(self) -> bool:
        return self._pending is not None

    async def approve(self, kind: str, summary: str) -> Decision:
        """Apply the level for `kind`, asking `summary` if it is ask_first, or a change while `careful`."""
        level = self.policy.level(kind)
        if level is ActionLevel.NEVER:
            log.info("refused a %s action", kind)
            return Decision(False, level, "refused")
        if level is not ActionLevel.ASK_FIRST and not (self.careful and level is ActionLevel.CHANGE):
            return Decision(True, level, "auto")
        answer = await self._ask(summary)
        return Decision(answer == "yes", level, answer)

    async def confirm(self, summary: str, *, detail: str = "") -> bool:
        """Confirmer: always ask. `detail` shows under the question in the Milo window, e.g. the whole task."""
        return await self._ask(summary, detail) == "yes"

    def answer(self, id: str, yes: bool, *, via: str = "button") -> bool:
        """Answer the waiting question `id`. False if it isn't the one waiting (already answered, timed out)."""
        if self._pending is None or self._pending[0] != id or self._pending[2].done():
            return False
        self._transcript.user("Yes" if yes else "No", via)
        self._pending[2].set_result(yes)
        return True

    def answer_text(self, text: str, *, via: str = "voice") -> bool:
        """Treat a turn as the answer if the waiting question is the last thing Milo said and the turn is
        a plain yes or no."""
        if self._pending is None or not self._still_showing(self._pending[1]):
            return False
        yes = yes_or_no(text)
        if yes is None:
            return False
        return self.answer(self._pending[0], yes, via=via)

    def _still_showing(self, question: str) -> bool:
        """The bubble shows the question, or the part of it spoken so far."""
        shown = self._ui.bubble.strip()
        return bool(shown) and question.startswith(shown)

    async def _ask(self, question: str, detail: str = "") -> str:
        """Returns "yes", "no" or "timeout"."""
        async with self._one_at_a_time:
            id = uuid.uuid4().hex[:12]
            future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self._pending = (id, question, future)
            log.info("asking before an action: %s", private(question))
            self._ui.emit(Confirm(id, question))
            self._transcript.say(f"{question}\n\n{detail}" if detail else question, Emotion.THINKING)
            self._speaker.say(question, Emotion.THINKING, speak=self._speak and not self._quiet())
            answer = "no"
            try:
                answer = "yes" if await asyncio.wait_for(future, self._timeout_s) else "no"
            except TimeoutError:
                answer = "timeout"
                self._transcript.say(NO_ANSWER, Emotion.NEUTRAL)
            finally:
                self._pending = None
                self._ui.emit(ConfirmDone(id, answer))
            log.info("the answer was %s", answer)
            return answer
