"""What the tags of one reply may do without the user's yes (ADR 0010, 0014, 0022, 0024).

Text from outside (a task result, a page on the screen, an invite in <today>) could have talked the talker into a
tag. So LiveTalk works out one `TagPolicy` per reply, from what its conversation has read, and every tag of that
reply follows it: an <open> of an address or a file, the act tags, <write>, <remember>, <reminder>, <task>,
<steer> and <routine>.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORK = re.compile(r"\b((fix|fill|put|add|make|change|update|correct|write|enter|insert|sort|format|create|build|"
                   r"finish|complete|edit|move|rename|copy|paste|replace|open|go|show|play|send|remind|check|find|"
                   r"summari[sz]e|start|stop|set|take)(es|s|ed|d|ing)?|"
                   r"(mach|füll|änder|korrigier|trag|schreib|erstell|sortier|formatier|bearbeit|füg|erledig|"
                   r"kopier|ersetz|verschieb|benenn|öffne|zeig|spiel|schick|erinner|stell)\w*)\b", re.IGNORECASE)
_QUESTION = re.compile(r"^\s*(what|why|how|who|whom|whose|where|when|which|is|are|was|were|does|did|do|has|have|"
                       r"was|warum|wieso|weshalb|wie|wer|wo|wann|welche\w*|ist|sind|hat|haben)\b", re.IGNORECASE)


_PLEASE = re.compile(r"^\s*(?:(?:yes|yeah|ok|okay|please|so|and|ja|bitte|also|und)\b[\s,.!]*)*"
                     r"(?:(?:can|could|would|will) you|(?:kannst|könntest|würdest) du)\b", re.IGNORECASE)


def asks_for_work(text: str) -> bool:
    """Whether the user's own words ask Milo to do something, not only to look or explain: "fix this sheet",
    "yes, open Chrome", "can you summarize the PDF", "füll das aus". "Can you …" and "kannst du …" with such a
    verb are requests. A question ("what is this?", "why is it red?", "can you see my screen?") never is. In auto
    mode only then may a task from the reply to what he saw start without a question."""
    if not _WORK.search(text):
        return False
    return bool(_PLEASE.search(text)) or not _QUESTION.search(text)


@dataclass(frozen=True)
class TagPolicy:
    """One reply's rules for its tags."""

    tainted: bool = False
    """Task results, meeting words or untrusted memories are in the conversation: outside text can steer every later
    reply in it, until it starts fresh."""
    saw_screen: bool = False
    """The conversation has read screen data, in this reply or an earlier one."""
    now: bool = False
    """The message being answered carries outside text: screen data, or another person's line in <today>."""
    at_mac: bool = False
    """Auto mode (ADR 0022) and the turn came from the Mac, by voice or typed."""
    own_work: bool = False
    """At the Mac in auto mode, the user's own words this turn asked for work (`asks_for_work`)."""

    @property
    def open_outside(self) -> bool:
        """An address or a file the user's words didn't name waits for a yes."""
        return self.tainted or self.now or self.saw_screen

    @property
    def act_outside(self) -> bool:
        """The act tags ask first, as careful actions."""
        return self.tainted or self.now

    @property
    def write_outside(self) -> bool:
        """<write> isn't pasted unless the user's own words asked for it (Writer decides)."""
        return self.tainted or self.now or self.saw_screen

    @property
    def ask_remember(self) -> bool:
        return self.tainted or self.now

    @property
    def ask_remind(self) -> bool:
        return self.tainted or self.now

    @property
    def ask_tasks(self) -> bool:
        """A task or a steer asks before it starts.

        Auto mode (ADR 0022, 0024): at the Mac a task never asks to start. When the user's own words asked for work
        ("fix this sheet", "mach die Mappe rot") that request is the yes for the whole task, even after Milo read the
        screen or other outside text. Otherwise ("what's this?", "thanks" after a task result) the task still
        starts, since reading never asks, but runs careful: before it changes anything it asks, so text Milo read
        can't turn into changes nobody asked for. Messages from the phone keep the plain rule."""
        return (self.tainted or self.now) and not self.at_mac

    @property
    def ask_routines(self) -> bool:
        """A routine is a recipe that may do a lot unattended: outside text can't start one without a yes."""
        return (self.tainted or self.now) and not self.own_work

    @property
    def careful(self) -> bool:
        """Its helpers ask before they change anything, not only before what can't be undone."""
        return (self.saw_screen or self.tainted or self.now) and not self.own_work

    @property
    def user_asked(self) -> bool:
        """The user asked for the work (auto mode lets its helper go further without a question)."""
        return self.own_work or not (self.tainted or self.now)


def policy(*, tainted: bool, saw_screen: bool, now: bool, auto: bool, via: str, request: str) -> TagPolicy:
    """The policy for a reply. `auto`: `[approvals] ask` is "auto". `via`: "voice", "typed" or "message".
    `request`: the user's own words this turn."""
    at_mac = auto and via in ("voice", "typed")
    return TagPolicy(tainted=tainted, saw_screen=saw_screen, now=now, at_mac=at_mac,
                     own_work=at_mac and asks_for_work(request))
