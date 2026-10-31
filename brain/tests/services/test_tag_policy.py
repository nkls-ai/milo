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
def test_in_auto_mode_at_the_mac_what_can_be_undone_just_happens(field):
    """An address, an act and <write> (ADR 0028's update); a file, a fact and a reminder still ask."""
    assert TagPolicy(**{field: True}).ask_undoable
    rule = TagPolicy(**{field: True}, at_mac=True)
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
