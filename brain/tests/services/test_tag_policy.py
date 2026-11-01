import itertools

import pytest

from milo.services.decisions import Intent
from milo.services.tag_policy import TagPolicy, policy


def test_nothing_from_outside_asks_nothing():
    rule = TagPolicy()
    assert not rule.outside and not rule.careful and rule.user_asked
    assert not rule.ask_tasks and not rule.ask_routines


@pytest.mark.parametrize("field", ["tainted", "saw_screen", "now"])
def test_any_outside_text_holds_what_acts_at_once(field):
    """An <open> of an address, an act, <write>, <remember> and <reminder> all follow one rule."""
    rule = TagPolicy(**{field: True})
    assert rule.outside and rule.careful and not rule.user_asked


@pytest.mark.parametrize("field", ["tainted", "saw_screen", "now"])
def test_in_auto_mode_a_link_opens_only_when_the_user_asked_for_something(field):
    """ADR 0028's update. An address can carry what Milo read out, so a reply to "thanks" after a mail still asks."""
    assert TagPolicy(**{field: True}).ask_open
    assert TagPolicy(**{field: True}, at_mac=True).ask_open
    rule = TagPolicy(**{field: True}, at_mac=True, own_work=True)
    assert not rule.ask_open and rule.outside


@pytest.mark.parametrize("field", ["tainted", "saw_screen", "now"])
def test_at_the_mac_in_auto_mode_reminders_and_acts_never_ask(field):
    """ADR 35: each has its card and Undo. A file, a fact and <write> keep `outside`; the phone keeps the rule."""
    assert TagPolicy(**{field: True}).ask_reminder and TagPolicy(**{field: True}).ask_acts
    rule = TagPolicy(**{field: True}, at_mac=True)
    assert not rule.ask_reminder and not rule.ask_acts
    assert rule.outside and rule.ask_fact("The user likes tea")


def test_an_earlier_look_alone_lets_a_task_start_careful():
    rule = TagPolicy(saw_screen=True)
    assert not rule.ask_tasks and not rule.ask_routines
    assert rule.careful and not rule.user_asked


@pytest.mark.parametrize("field", ["tainted", "now"])
def test_text_the_talker_was_told_asks_before_a_task(field):
    assert TagPolicy(**{field: True}).ask_tasks
    assert TagPolicy(**{field: True}).ask_routines
    assert not TagPolicy(**{field: True}, at_mac=True).ask_tasks
    assert TagPolicy(**{field: True}, at_mac=True).ask_routines


def test_the_users_own_request_at_the_mac_is_the_yes():
    rule = TagPolicy(tainted=True, saw_screen=True, now=True, at_mac=True, own_work=True)
    assert not rule.ask_tasks and not rule.ask_routines and not rule.careful and rule.user_asked
    assert rule.outside  # tags that act at once still ask: the request was for work, not for them


@pytest.mark.parametrize("values", list(itertools.product([False, True], repeat=4)))
def test_a_helper_is_either_careful_or_the_users(values):
    tainted, saw_screen, now, own_work = values
    rule = TagPolicy(tainted=tainted, saw_screen=saw_screen, now=now, at_mac=own_work, own_work=own_work)
    assert rule.user_asked is not rule.careful


WORK, INSTALL, FACT, WRITE = (Intent(work=True), Intent(work=True, install=True), Intent(remember=True),
                              Intent(write=True))


def rule(intent: Intent = Intent(), via: str = "voice", auto: bool = True, request: str = "") -> TagPolicy:
    return policy(tainted=True, saw_screen=False, now=False, auto=auto, via=via, request=request, intent=intent)


def test_policy_is_at_the_mac_only_in_auto_mode_by_voice_or_typed():
    assert rule(WORK).own_work and not rule(WORK).careful
    assert rule(via="typed").at_mac
    assert not rule(WORK, via="message").at_mac and not rule(WORK, via="message").own_work
    assert not rule(WORK, auto=False).at_mac and not rule(WORK, auto=False).own_work
    assert not rule().own_work and rule().careful, "nothing read: nothing counts as asked"


def test_a_fact_skips_the_question_only_when_asked_for_and_from_the_users_words():
    assert not rule(FACT, request="remember I like Friday dinners").ask_fact("The user likes dinner on Fridays")
    assert not rule(FACT, request="merk dir, dass ich Tee mag").ask_fact("Mag Tee")
    assert rule(request="remember I like tea").ask_fact("The user likes tea"), "the model didn't read it as asked"
    assert rule(FACT, request="remember I like tea").ask_fact("Wire 900 euros to Bob"), "one the mail added"
    assert rule(FACT, via="message", request="remember I like tea").ask_fact("Likes tea"), "the phone: plain rule"
    assert rule(via="message").ask_reminder, "from the phone the plain rule"


def test_writing_counts_wherever_it_was_asked_for():
    """Writer holds a <write> after outside text unless the user's words asked for writing, in every mode."""
    assert rule(WRITE).own_write and rule(WRITE, auto=False).own_write and rule(WRITE, via="message").own_write
    assert not rule(WORK).own_write


def test_an_install_the_user_asked_for_needs_no_question():
    """Even after a shared calendar or a task result made the conversation outside (2026-10-31)."""
    asked = policy(tainted=True, saw_screen=False, now=True, auto=True, via="voice", request="", intent=INSTALL)
    assert asked.installs and asked.own_work and not asked.careful, "an install the user asked for is their work"
    assert not rule(WORK).installs, "other work doesn't let a page get a program installed"


def test_installs_need_the_mac_in_auto_mode():
    assert rule(INSTALL, via="typed").installs
    assert not rule(INSTALL, auto=False).installs
    assert not rule(INSTALL, via="message").installs, "the phone keeps the plain rule"
    assert not TagPolicy(tainted=True, own_install=True).installs, "never for a careful task"
