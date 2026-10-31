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
                   r"summari[sz]e|start|stop|set|take|search|google|look up|delete|remove|cancel|schedule|save|archive)"
                   r"(es|s|ed|d|ing)?|"
                   r"(mach|füll|änder|korrigier|trag|schreib|erstell|sortier|formatier|bearbeit|füg|erledig|"
                   r"kopier|ersetz|verschieb|benenn|öffne|zeig|spiel|schick|erinner|stell|such|lösch|entfern|absag|"
                   r"speicher|notier|plan)\w*)\b", re.IGNORECASE)
_QUESTION = re.compile(r"^\s*(what|why|how|who|whom|whose|where|when|which|is|are|was|were|does|did|do|has|have|"
                       r"was|warum|wieso|weshalb|wie|wer|wo|wann|welche\w*|ist|sind|hat|haben)\b", re.IGNORECASE)


# The user's own words ask for this very tag: only then may it skip outside text's question.
_REMIND = re.compile(r"\b(remind(s|ed|er)?|erinner(e|n|st|t|ung)?)\b", re.IGNORECASE)
_REMEMBER = re.compile(r"\b(remember|keep in mind|merk(e|en|st)? (dir|euch|Ihnen))\b", re.IGNORECASE)


_NOT = re.compile(r"\b(don'?t|do not|never|nicht|nie|kein\w*)\b", re.IGNORECASE)


_PLEASE = re.compile(r"^\s*(?:(?:yes|yeah|ok|okay|please|so|and|ja|bitte|also|und)\b[\s,.!]*)*"
                     r"(?:(?:can|could|would|will) you|(?:kannst|könntest|würdest) du)\b", re.IGNORECASE)


def _asks(verb: re.Pattern, text: str) -> bool:
    """The words ask for it: the verb, in a request ("remind me", "can you remind me"), not in a question ("did you
    remind me?") or a no ("don't remind me", "erinner mich nicht")."""
    return verb.search(text) is not None and not _NOT.search(text) \
        and (bool(_PLEASE.search(text)) or not _QUESTION.search(text))


def _from_request(item: str, request: str) -> bool:
    """The reminder or fact carries a word of the user's own request ("Call Anna" for "remind me to call Anna"), so
    outside text can't add one of its own next to the one asked for."""
    def stems(text: str) -> set[str]:  # "Fridays" and "Friday" alike
        return {w[:5] for w in re.findall(r"[^\W_]{3,}", text.lower())}

    return bool(stems(item) & stems(request))


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
    own_reminder: bool = False
    """At the Mac in auto mode, the user's own words asked for a reminder ("remind me", "erinnere mich")."""
    own_fact: bool = False
    """At the Mac in auto mode, the user's own words asked Milo to remember something ("remember", "merk dir")."""
    request: str = ""
    """The user's own words this turn."""

    @property
    def outside(self) -> bool:
        """The conversation has read outside text: every tag that takes effect at once waits for a yes. An <open> of
        a file always, and <write> goes in only when the user's own words asked for writing (Writer decides); the
        others as `ask_undoable`, `ask_reminder()` and `ask_fact()` say."""
        return self.tainted or self.now or self.saw_screen

    def ask_reminder(self, what: str) -> bool:
        """A <reminder> after outside text asks, since open reminders go into every later <today>; unless the user's
        own words asked for this one ("remind me to call Anna" on a day with shared calendar entries)."""
        return self.outside and not (self.own_reminder and _from_request(what, self.request))

    def ask_fact(self, fact: str) -> bool:
        """A <remember> after outside text asks, since facts steer every later conversation; unless the user's own
        words asked Milo to remember this."""
        return self.outside and not (self.own_fact and _from_request(fact, self.request))

    @property
    def ask_undoable(self) -> bool:
        """An <open> of an address the user's words didn't name and an act tag (as a careful action). Each can be
        closed or undone, so in auto mode at the Mac, when the user's own message asks for something (`own_work`:
        "open the link", "add that to my calendar"), it just happens even after outside text (ADR 0022, 0028):
        sending, deleting for good and paying still ask (Approvals). A reply to "thanks" after a mail still asks:
        only the mail could have put an action there."""
        return self.outside and not self.own_work

    @property
    def careful(self) -> bool:
        """A task, a steer or a routine run from this reply runs careful: its helper asks before it changes
        anything, not only before what can't be undone. Unless the user's own words asked for the work."""
        return self.outside and not self.own_work

    @property
    def user_asked(self) -> bool:
        """The user asked for the work: in auto mode its helper goes on without a question. Never for a careful
        helper, so its questions are asked."""
        return not self.careful

    @property
    def _steered(self) -> bool:
        """Outside text the talker was told, not only shown: task results, meeting words, untrusted memories, or the
        message being answered. A look in an earlier turn alone lets a helper start, careful (ADR 0014)."""
        return self.tainted or self.now

    @property
    def ask_tasks(self) -> bool:
        """A task or a steer asks before it starts.

        Auto mode (ADR 0022, 0024): at the Mac a task never asks to start. When the user's own words asked for work
        ("fix this sheet", "mach die Mappe rot") that request is the yes for the whole task, even after Milo read the
        screen or other outside text. Otherwise ("what's this?", "thanks" after a task result) the task still
        starts, since reading never asks, but runs careful: before it changes anything it asks, so text Milo read
        can't turn into changes nobody asked for. Messages from the phone keep the plain rule."""
        return self._steered and not self.at_mac

    @property
    def ask_routines(self) -> bool:
        """A routine is a recipe that may do a lot unattended: outside text can't start one without a yes, unless
        the user's own words asked for work."""
        return self._steered and not self.own_work


def policy(*, tainted: bool, saw_screen: bool, now: bool, auto: bool, via: str, request: str) -> TagPolicy:
    """The policy for a reply. `auto`: `[approvals] ask` is "auto". `via`: "voice", "typed" or "message".
    `request`: the user's own words this turn."""
    at_mac = auto and via in ("voice", "typed")
    return TagPolicy(tainted=tainted, saw_screen=saw_screen, now=now, at_mac=at_mac,
                     own_work=at_mac and asks_for_work(request),
                     own_reminder=at_mac and _asks(_REMIND, request),
                     own_fact=at_mac and _asks(_REMEMBER, request), request=request)
