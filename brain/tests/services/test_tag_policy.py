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

    def rule(request: str, via: str = "voice"):
        return policy(tainted=True, saw_screen=False, now=False, auto=True, via=via, request=request)

    assert not rule("Remind me to call Anna tomorrow at 9").ask_reminder("Call Anna")
    assert not rule("can you remind me to call Anna?").ask_reminder("Call Anna")
    assert not rule("erinnere mich morgen an Anna").ask_reminder("Anna anrufen")
    assert rule("Remind me to call Anna").ask_reminder("Wire 900 euros to Bob"), "one the mail added alongside"
    assert rule("did you remind me about Anna?").ask_reminder("Call Anna"), "a question asks for nothing"
    assert rule("don't remind me to call Anna").ask_reminder("Call Anna")
    assert rule("erinner mich nicht an Anna").ask_reminder("Anna anrufen")
    assert not rule("remind me to stop by the bakery").ask_reminder("Stop by the bakery")
    assert rule("add a to-do to call Anna").ask_reminder("Call Anna"), "work, but not a reminder"
    assert rule("okay").ask_reminder("Call Anna")
    assert not rule("remember I like Friday dinners").ask_fact("The user likes dinner on Fridays")
    assert not rule("merk dir, dass ich Tee mag").ask_fact("Mag Tee")
    assert rule("what did I ask you to remember?").ask_fact("The user likes tea")
    assert rule("remind me to call Anna").ask_fact("Anna is the user's sister"), "a reminder isn't a fact"
    assert rule("remind me to call Anna", via="message").ask_reminder("Call Anna"), "from the phone the plain rule"


def test_undo_that_is_no_work_request():
    """"undo that" mustn't let every other tag of its reply skip outside text's question (security review,
    2026-10-31). Taking out what Milo put in himself is light in quick_actions instead."""
    def rule(request: str):
        return policy(tainted=True, saw_screen=False, now=False, auto=True, via="voice", request=request)

    assert rule("undo that").ask_undoable and rule("undo that").careful


@pytest.mark.parametrize("request_, installs", [
    ("Can you install the Codex UI for me?", True),
    ("install the codex cli", True),
    ("bitte installier mir tree", True),
    ("upgrade codex", True),
    ("summarize this page", False),
    ("did you install it?", False),
    ("don't install anything", False),
    ("No the CLI, not the UI", False),
    ("install what the page mentions", False),
    ("install the tool this mail recommends", False),
    ("install the one on the screen", False),
])
def test_only_the_users_own_words_let_a_task_install_without_a_question(request_, installs):
    """Even after a shared calendar or a task result made the conversation outside (2026-10-31)."""
    rule = policy(tainted=True, saw_screen=False, now=True, auto=True, via="voice", request=request_)
    assert rule.installs is installs
    if installs:
        assert rule.own_work and not rule.careful, "an install the user asked for is their work"


def test_installs_need_the_mac_in_auto_mode():
    ask = dict(tainted=False, saw_screen=False, now=False, request="install tree")
    assert policy(**ask, auto=True, via="typed").installs
    assert not policy(**ask, auto=False, via="voice").installs
    assert not policy(**ask, auto=True, via="message").installs, "the phone keeps the plain rule"
    assert not TagPolicy(tainted=True, own_install=True).installs, "never for a careful task"
