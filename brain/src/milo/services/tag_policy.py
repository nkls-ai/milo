"""What the tags of one reply may do without the user's yes (ADR 0010, 0014, 0022, 0024).

Text from outside (a task result, a page on the screen, an invite in <today>) could have talked the talker into a
tag. So LiveTalk works out one `TagPolicy` per reply, from what its conversation has read, and every tag of that
reply follows it: an <open> of an address or a file, the act tags, <write>, <remember>, <reminder>, <task>,
<steer> and <routine>.

In auto mode at the Mac the small, plain-to-see things never ask because of outside text (ADR 0035): a reminder, a
calendar entry, a to-do, each with its card and Undo. What reaches other people or can't be undone asks anyway, further
down (Approvals, QuickActions). A link Milo would open and work for a helper still need the user's own words, since
an address can carry data out and a page shouldn't be able to start work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .decisions import Intent


def _from_request(item: str, request: str) -> bool:
    """The fact carries a word of the user's own request ("Likes tea" for "remember I like tea"), so outside text
    can't add one of its own next to the one asked for."""
    def stems(text: str) -> set[str]:  # "Fridays" and "Friday" alike
        return {w[:5] for w in re.findall(r"[^\W_]{3,}", text.lower())}

    return bool(stems(item) & stems(request))


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
    """At the Mac in auto mode, the user's own words this turn asked Milo to do something, not only to look or
    explain ("fix this sheet", "kannst du die in die Excel reinkopieren?"; not "what is this?" or "thanks"), as the
    decision model read them (services/decisions.py)."""
    own_install: bool = False
    """At the Mac in auto mode, the user's own words asked Milo to install something ("install the codex cli",
    "installier mir tree")."""
    own_fact: bool = False
    """At the Mac in auto mode, the user's own words asked Milo to remember something ("remember", "merk dir")."""
    own_write: bool = False
    """The user's own words asked for a text to be written ("answer this email", "schreib Anna"): then outside text
    read before can't be what started a <write> (Writer). Not "what does the reply say?"."""
    request: str = ""
    """The user's own words this turn, after the request they answer when Milo's last reply asked them something
    ("put lunch with Anna in tomorrow", "What time?", "at one")."""

    @property
    def outside(self) -> bool:
        """The conversation has read outside text: every tag that takes effect at once waits for a yes. An <open> of
        a file always, and <write> goes in only when the user's own words asked for writing (Writer decides); the
        others as `ask_open`, `ask_acts`, `ask_reminder` and `ask_fact()` say."""
        return self.tainted or self.now or self.saw_screen

    @property
    def ask_reminder(self) -> bool:
        """A <reminder> after outside text asks, since open reminders go into every later <today> (as data). Never at
        the Mac in auto mode (ADR 0035): its card has Undo, and "10 in the morning", the answer to Milo's question
        about a reminder, has no "remind" to tell it apart."""
        return self.outside and not self.at_mac

    @property
    def ask_acts(self) -> bool:
        """An act tag (a calendar entry, a to-do, a note, a timer…) runs as a careful action after outside text.
        Never at the Mac in auto mode (ADR 0035): each has its card and Undo, and what can't be undone or reaches
        other people (an invite, a shared list, a shortcut) asks in QuickActions anyway."""
        return self.outside and not self.at_mac

    def ask_fact(self, fact: str) -> bool:
        """A <remember> after outside text asks, since facts steer every later conversation; unless the user's own
        words asked Milo to remember this."""
        return self.outside and not (self.own_fact and _from_request(fact, self.request))

    @property
    def ask_open(self) -> bool:
        """An <open> of an address the user's words didn't name. A tab can be closed, so in auto mode at the Mac,
        when the user's own message asks for something (`own_work`: "open the link"), it just happens even after
        outside text (ADR 0022, 0028). A reply to "thanks" after a mail still asks: only the mail could have put the
        link there, and an address can carry what Milo read out to whoever wrote it."""
        return self.outside and not self.own_work

    @property
    def careful(self) -> bool:
        """A task, a steer or a routine run from this reply runs careful: its helper asks before it changes
        anything, not only before what can't be undone. Unless the user's own words asked for the work."""
        return self.outside and not self.own_work

    @property
    def installs(self) -> bool:
        """The user's own words asked for an install, so a task from this reply may install the packages those words
        name without a question (Helper.install_words, core/packages.named_by). Not for a careful helper, and not for
        one whose user asked only for other work, so a page or mail it reads can't get a program installed."""
        return self.own_install and not self.careful

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


def policy(*, tainted: bool, saw_screen: bool, now: bool, auto: bool, via: str, request: str,
           intent: Intent = Intent()) -> TagPolicy:
    """The policy for a reply. `auto`: `[approvals] ask` is "auto". `via`: "voice", "typed" or "message".
    `request`: the user's own words this turn. `intent`: what the decision model read in them; nothing asked when it
    hasn't answered (yet)."""
    at_mac = auto and via in ("voice", "typed")
    return TagPolicy(tainted=tainted, saw_screen=saw_screen, now=now, at_mac=at_mac,
                     own_work=at_mac and intent.work, own_install=at_mac and intent.install,
                     own_fact=at_mac and intent.remember, own_write=intent.write, request=request)
