import asyncio

import pytest

from milo.core.events import AppRequest, AppResponse, Bubble, Confirm, ConfirmDone
from milo.core.registry import ConfigError
from milo.core.types import ActionLevel, Decision
from milo.services.app_bridge import NOT_RUNNING, AppBridge
from milo.services.approvals import NO_ANSWER, ActionPolicy, yes_or_no
from milo.services.tool_requests import ToolRequests
from milo.services.transcript import Transcript
from tests.fakes import MemoryTranscript
from tests.services.stack import Stack, settle


def test_default_levels_follow_the_three_action_levels():
    p = ActionPolicy()
    assert p.level("read") is ActionLevel.READ and p.level("draft") is ActionLevel.READ
    assert p.level("change") is ActionLevel.CHANGE
    for kind in ("send", "share", "delete", "buy", "shortcut"):
        assert p.level(kind) is ActionLevel.ASK_FIRST
    for kind in ("password", "money", "security"):
        assert p.level(kind) is ActionLevel.NEVER
    assert p.level("launch_rockets") is ActionLevel.ASK_FIRST, "unknown kinds ask"


def test_levels_are_configurable_but_never_stays_never():
    assert ActionPolicy({"change": "ask_first", "shortcut": "change"}).level("change") is ActionLevel.ASK_FIRST
    with pytest.raises(ConfigError, match="always never"):
        ActionPolicy({"money": "ask_first"})
    with pytest.raises(ConfigError, match="unknown action"):
        ActionPolicy({"sned": "never"})
    with pytest.raises(ConfigError, match="must be one of"):
        ActionPolicy({"send": "maybe"})


@pytest.mark.parametrize("text, answer", [
    ("Yes.", True), ("yeah, go ahead", True), ("Okay!", True), ("ja bitte", True), ("Sure, send it", True),
    ("No.", False), ("nope", False), ("don't", False), ("Nein, lieber nicht", False), ("not now", False),
    ("Stop!", False), ("what's the weather tomorrow", None), ("", None), ("now", None),
    ("yes but first tell me who Anna is and why", None),
])
def test_yes_or_no(text, answer):
    assert yes_or_no(text) is answer


def ask(s: Stack, coro_fn, *, then=None):
    async def run():
        task = asyncio.create_task(coro_fn())
        await settle()
        if then is not None:
            then()
        await settle()
        return await task

    return asyncio.run(run())


def test_read_and_change_happen_without_a_question():
    s = Stack()
    assert ask(s, lambda: s.approvals.approve("read", "Look?")) == Decision(True, ActionLevel.READ, "auto")
    assert ask(s, lambda: s.approvals.approve("change", "Add?")) == Decision(True, ActionLevel.CHANGE, "auto")
    assert not s.sink.of(Confirm)


def test_never_is_refused_without_a_question():
    s = Stack()
    assert ask(s, lambda: s.approvals.approve("money", "Transfer?")) == Decision(False, ActionLevel.NEVER, "refused")
    assert not s.sink.of(Confirm)


def test_ask_first_shows_and_speaks_the_question_and_a_click_answers_it():
    s = Stack()
    question = "I'm about to send this to Anna. Send it?"

    def click():
        [c] = s.sink.of(Confirm)
        assert c.question == question
        assert s.approvals.answer(c.id, True)

    assert ask(s, lambda: s.approvals.approve("send", question), then=click) == \
        Decision(True, ActionLevel.ASK_FIRST, "yes")
    assert " ".join(s.voice.spoken) == question and Bubble(question) in s.sink.events
    assert [d.answer for d in s.sink.of(ConfirmDone)] == ["yes"]
    assert not s.approvals.pending


def test_no_answer_means_no():
    store = MemoryTranscript()
    s = Stack(confirm_timeout_s=0.05)
    s.approvals._transcript = Transcript(s.ui, store, s.clock)
    assert ask(s, lambda: s.approvals.confirm("Delete all 40 photos?")) is False
    assert [d.answer for d in s.sink.of(ConfirmDone)] == ["timeout"]
    assert [e["text"] for e in store.entries] == ["Delete all 40 photos?", NO_ANSWER]


def test_an_old_or_unknown_answer_is_ignored():
    s = Stack(confirm_timeout_s=0.05)
    assert not s.approvals.answer("nope", True)
    assert ask(s, lambda: s.approvals.confirm("Send it?"), then=lambda: s.approvals.answer("other", True)) is False


def test_questions_wait_their_turn():
    s = Stack()

    async def run():
        first = asyncio.create_task(s.approvals.confirm("First?"))
        second = asyncio.create_task(s.approvals.confirm("Second?"))
        await settle()
        assert [c.question for c in s.sink.of(Confirm)] == ["First?"]
        s.approvals.answer_text("no")
        await settle()
        assert [c.question for c in s.sink.of(Confirm)] == ["First?", "Second?"]
        s.approvals.answer_text("yes")
        return await first, await second

    assert asyncio.run(run()) == (False, True)


def test_the_question_is_silent_while_the_user_is_mid_turn():
    s = Stack()
    s.approvals._quiet = lambda: True
    ask(s, lambda: s.approvals.confirm("Send it?"), then=lambda: s.approvals.answer_text("yes"))
    assert s.voice.spoken == [] and Bubble("Send it?") in s.sink.events


def test_tool_requests_approve_confirm_and_reach_the_app():
    s = Stack()
    requests = ToolRequests(s.approvals, s.bridge)

    async def run():
        read = await requests.handle({"op": "approve", "kind": "read", "summary": "Look in the calendar"})
        asking = asyncio.create_task(requests.handle({"op": "confirm", "summary": "Run “Text Anna”?"}))
        await settle()
        s.approvals.answer_text("yes")
        confirmed = await asking
        app = asyncio.create_task(requests.handle({"op": "app", "name": "calendar.events",
                                                    "args": {"start": "2026-10-30T00:00:00"}}))
        await settle()
        [req] = s.sink.of(AppRequest)
        assert req.op == "calendar.events" and req.args == {"start": "2026-10-30T00:00:00"}
        await s.brain.handle(AppResponse(req.id, True, [{"title": "Dentist"}]))
        bad = await requests.handle({"op": "app", "name": "mail.send", "args": {}})
        missing = await requests.handle({"op": "confirm"})
        unknown = await requests.handle({"op": "launch"})
        return read, confirmed, await app, bad, missing, unknown

    read, confirmed, app, bad, missing, unknown = asyncio.run(run())
    assert read == {"ok": True, "result": {"allowed": True, "level": "read", "answer": "auto"}}
    assert confirmed == {"ok": True, "result": {"yes": True}}
    assert app == {"ok": True, "result": [{"title": "Dentist"}]}
    assert not bad["ok"] and not missing["ok"] and not unknown["ok"]


def test_the_app_bridge_reports_app_errors_and_a_missing_app_plainly():
    s = Stack()

    async def run():
        failing = asyncio.create_task(s.bridge.call("reminders.list", {}))
        await settle()
        [req] = s.sink.of(AppRequest)
        s.bridge.resolve(AppResponse(req.id, False, error="Milo isn't allowed to use your reminders."))
        with pytest.raises(Exception, match="isn't allowed"):
            await failing
        offline = AppBridge(s.ui, connected=lambda: False)
        with pytest.raises(Exception, match=NOT_RUNNING):
            await offline.call("reminders.list", {})
        silent = AppBridge(s.ui, timeout_s=0.01)
        with pytest.raises(Exception, match="didn't answer"):
            await silent.call("reminders.list", {})

    asyncio.run(run())


def test_app_ops_check_the_switch_and_apply_their_level_on_this_side():
    s = Stack()
    s.approvals.policy = ActionPolicy({"change": "ask_first"})
    requests = ToolRequests(s.approvals, s.bridge, enabled=["calendar"])

    async def run():
        off = await requests.handle({"op": "app", "name": "reminders.list", "args": {}})
        adding = asyncio.create_task(requests.handle({"op": "app", "name": "calendar.add_event",
                                                      "args": {"title": "Doctor"},
                                                      "summary": "Put “Doctor” in your calendar?"}))
        await settle()
        [c] = s.sink.of(Confirm)
        assert c.question == "Put “Doctor” in your calendar?"
        s.approvals.answer(c.id, False)
        return off, await adding

    off, refused = asyncio.run(run())
    assert off == {"ok": False, "error": "The reminders connection is switched off in Milo's settings."}
    assert refused == {"ok": False, "error": "The user said no."}
    assert not s.sink.of(AppRequest), "nothing reached the app"
