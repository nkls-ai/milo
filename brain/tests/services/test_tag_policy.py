import itertools

import pytest

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
def test_in_auto_mode_what_the_user_asked_for_just_happens_if_it_can_be_undone(field):
    """An address and an act (ADR 0028's update); a file, a fact, a reminder and <write> keep `outside`."""
    assert TagPolicy(**{field: True}).ask_undoable
    assert TagPolicy(**{field: True}, at_mac=True).ask_undoable, "a reply to \"thanks\" after a mail still asks"
    rule = TagPolicy(**{field: True}, at_mac=True, own_work=True)
    assert not rule.ask_undoable and rule.outside


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


def test_policy_is_at_the_mac_only_in_auto_mode_by_voice_or_typed():
    assert policy(tainted=True, saw_screen=False, now=False, auto=True, via="voice", request="fix this").own_work
    assert policy(tainted=True, saw_screen=False, now=False, auto=True, via="typed", request="x").at_mac
    assert not policy(tainted=True, saw_screen=False, now=False, auto=True, via="message", request="fix it").at_mac
    assert not policy(tainted=True, saw_screen=False, now=False, auto=False, via="voice", request="fix it").at_mac
    assert not policy(tainted=True, saw_screen=False, now=False, auto=True, via="voice",
                      request="what is this?").own_work


def test_only_words_that_ask_for_the_tag_itself_let_it_skip_the_question():
    from milo.services.tag_policy import policy

    def rule(request: str):
        return policy(tainted=True, saw_screen=False, now=False, auto=True, via="voice", request=request)

    assert not rule("Remind me to call Anna tomorrow at 9").ask_reminder
    assert not rule("erinnere mich morgen an Anna").ask_reminder
    assert rule("add a to-do to call Anna").ask_reminder, "work, but not a reminder"
    assert rule("okay").ask_reminder
    assert not rule("remember I like Friday dinners").ask_fact
    assert not rule("merk dir, dass ich Tee mag").ask_fact
    assert rule("remind me to call Anna").ask_fact, "a reminder isn't a fact"
    assert policy(tainted=True, saw_screen=False, now=False, auto=True, via="message",
                  request="remind me to call Anna").ask_reminder, "from the phone the plain rule holds"
