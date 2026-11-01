"""What the user's own words ask for, and sorting for helpers, read by the decision model (ADR 0040).

`Decisions.intent` reads one turn's request: work, an install, a fact to keep, a text to write. The tag policy
(tag_policy.py) lets a reply go on without a question after outside text only for what these say the user asked
for. The model sees only the user's own words, never a page, a mail or a task result, so outside text can't sway
it. When there is no model, it fails, or it is slower than `wait_s`, nothing counts as asked: Milo asks first.

`Decisions.classify` is the helpers' `classify` tool: items sorted into classes the helper names.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from milo.core.decide import Answer, Choice, Decider, YesNo

log = logging.getLogger("milo.decisions")

MAX_ITEMS = 200
"""Items one `classify` call sorts: about a third of a second each on the Mac's GPU."""
MAX_CLASSES = 50
IDLE_S = 60.0
"""Unused this long, the model may have been paged out: the talk key wakes it (`wake`)."""

ASKS = {
    "work": Choice("What does the user want from the assistant?", {
        "action": "it should do something for them: open, change, make, fill in, copy, find, send, play, set or remind",
        "look": "it should only look at, read or explain something",
        "question": "an answer to a question, or its opinion",
        "undo": "it should undo or take back what it just did",
        "chat": "thanks, a greeting, or a remark"}),
    "task": YesNo("Is this a request for the assistant to carry out an action or task (on the computer, in an app, "
                  "with files, or at home), rather than a question to answer, a remark or thanks?"),
    "install": YesNo("Does the user ask to install, update or upgrade a specific program by its name? Answer no when "
                     "the program is only described by where it is mentioned (a page, mail, file or the screen) and "
                     "not named."),
    "remember": YesNo("Does the user give the assistant a new fact or preference about themselves to keep in memory "
                      "('remember that I ...', 'merk dir, dass ...')? A question about what was remembered, a "
                      "reminder, or any other task is no."),
    "write": YesNo("Does the user ask the assistant to write or rewrite a text (a message, email, reply, summary or "
                   "translation)? Reminders, tables, notes, jokes and questions are no."),
}
"""The questions about a request, worded for the model and picked on the user's own sentences
(tests/eval/test_decisions.py). A choice is yes for its first option: "undo that" and "look at my screen" are
requests too, but not for work, so they have options of their own."""
ASKED = {"work": (("work", "task"), 0.4), "install": (("install",), 0.5), "remember": (("remember",), 0.5),
         "write": (("write",), 0.6)}
"""What counts as asked: the mean of these answers above this. Work is two questions, one choice and one yes-or-no;
each alone missed requests ("how about you list all the links in a sheet", "look at my screen and fix this sheet")
that together they find, and neither counts "undo that" or "look at my screen". On 112 sentences in German, English,
French and Spanish: no request missed, three questions taken for work ("what can you open?"). An install of what a
page mentions can still read as asked; core/packages.named_by then wants the package's own name in the user's words."""


@dataclass(frozen=True)
class Intent:
    """What the user's own words asked for. All False: nothing, or nobody could tell."""

    work: bool = False
    install: bool = False
    remember: bool = False
    write: bool = False


class Decisions:
    def __init__(self, decider: Decider | None, *, wait_s: float = 8.0,
                 executor: concurrent.futures.Executor | None = None):
        self._decider = decider
        self._wait_s = wait_s
        self._executor = executor or concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="decide")
        self._used = time.monotonic()

    @property
    def available(self) -> bool:
        return self._decider is not None

    async def warm(self) -> None:
        """Load the model at start, so the first turn doesn't wait for it."""
        if self._decider is None:
            return
        try:
            await asyncio.get_running_loop().run_in_executor(self._executor, self._decider.warm)
        except Exception:
            log.exception("the decision model didn't load: nothing counts as asked, so Milo asks first")

    def wake(self) -> None:
        """The user started talking: page the model back in while they speak. After a night idle macOS had moved
        its weights out, and the first two readings took longer than `wait_s`. Its queue is one thread, so the
        reading of what they say waits behind this. Must be called on the event loop."""
        if self._decider is None or time.monotonic() - self._used < IDLE_S:
            return
        self._used = time.monotonic()
        decider = self._decider

        def wake() -> None:
            started = time.monotonic()
            decider.warm()
            if (took := time.monotonic() - started) > 0.5:
                log.info("woke the decision model in %.2fs (paged out while idle)", took)

        def failed(woken: asyncio.Future) -> None:
            if not woken.cancelled() and woken.exception() is not None:
                log.warning("waking the decision model failed: %s", woken.exception())

        asyncio.get_running_loop().run_in_executor(self._executor, wake).add_done_callback(failed)

    def _decide(self, text: str, questions: Mapping[str, YesNo | Choice]) -> dict[str, Answer | None]:
        started = time.monotonic()
        try:
            return self._decider.decide(text, questions)
        finally:
            self._used = time.monotonic()
            if (took := self._used - started) > self._wait_s:
                log.info("a reading took %.2fs, longer than [decide] wait_s", took)

    async def intent(self, request: str) -> Intent:
        """What `request`, the user's own words, asks for. Never raises; Intent() when it can't tell in time."""
        if self._decider is None or not request.strip():
            return Intent()
        loop = asyncio.get_running_loop()
        started = time.monotonic()
        try:
            answers = await asyncio.wait_for(
                loop.run_in_executor(self._executor, self._decide, request, ASKS), self._wait_s)
        except TimeoutError:
            log.info("the decision model took longer than %.1fs: nothing counts as asked", self._wait_s)
            return Intent()
        except Exception:
            log.exception("the decision model failed: nothing counts as asked")
            return Intent()
        said = {name: sum(_yes(ASKS[k], answers.get(k)) for k in keys) / len(keys) > at
                for name, (keys, at) in ASKED.items()}
        intent = Intent(**said)
        log.info("asked for %s (read in %.2fs)", ", ".join(k for k, v in said.items() if v) or "nothing",
                 time.monotonic() - started)
        return intent

    async def classify(self, items: Sequence[str], classes: Mapping[str, str], question: str = "") -> list[dict]:
        """Each item sorted into one of `classes` (name -> what belongs there): {"class", "confidence",
        "probabilities"}, or {"error"} for an item the model can't read. Raises ValueError for a bad call."""
        if self._decider is None:
            raise ValueError("Milo has no decision model here ([decide] use is \"none\").")
        if not items:
            return []
        if len(items) > MAX_ITEMS:
            raise ValueError(f"At most {MAX_ITEMS} items per call.")
        if not 2 <= len(classes) <= MAX_CLASSES:
            raise ValueError(f"Give between 2 and {MAX_CLASSES} classes.")
        choice = {"c": Choice(question.strip() or "Which class does this belong to?",
                              {str(k): str(v) for k, v in classes.items()})}
        def run() -> list[dict]:
            out = []
            for item in items:
                p = self._decide(str(item), choice).get("c")
                if not isinstance(p, dict) or not p:
                    out.append({"error": "The model couldn't read this one (too long?)."})
                    continue
                best = max(p, key=p.__getitem__)
                out.append({"class": best, "confidence": round(p[best], 3),
                            "probabilities": {k: round(v, 3) for k, v in p.items()}})
            return out

        return await asyncio.get_running_loop().run_in_executor(self._executor, run)


def _yes(question: YesNo | Choice, answer: Answer | None) -> float:
    """The probability of yes: of a choice's first option. 0 for no answer."""
    if isinstance(answer, dict) and isinstance(question, Choice):
        return answer.get(next(iter(question.options)), 0.0)
    return answer if isinstance(answer, float) else 0.0
