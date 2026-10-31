"""A question nobody answers yet stays open, is asked once more by voice, and never drops the work (ADR 0031).

The night of 2026-10-30 Milo asked "Should I go ahead with this: Open Microsoft Excel …?", heard nothing for 60 s,
said "No answer, so I left it." and dropped a task the user had asked for.
"""

import asyncio

from milo.core.events import Confirm, ConfirmDone
from milo.core.types import Emotion, Reply, Usage
from milo.services import orchestrator
from milo.services.helpers import HelperStatus
from milo.services.orchestrator import HelperQuestions
from tests.services.stack import Stack, settle

QUESTION = "Send the mail to Anna?"


def test_an_unanswered_question_stays_open_and_is_asked_once_more_by_voice():
    s = Stack(confirm_timeout_s=0)
    s.approvals._reask_s = 0.05

    async def run():
        task = asyncio.create_task(s.approvals.confirm(QUESTION))
        await asyncio.sleep(0.4)
        assert not task.done() and s.approvals.pending and not s.sink.of(ConfirmDone)
        assert s.voice.spoken == [QUESTION, QUESTION], "asked again once, not every 20 s"
        assert s.approvals.answer_text("yes"), "the bubble shows the question again, so a spoken yes counts"
        return await task

    assert asyncio.run(run()) is True


def test_the_second_ask_waits_until_the_user_stops_talking():
    s = Stack(confirm_timeout_s=0)
    s.approvals._reask_s = 0.05
    talking = [True]
    s.approvals._quiet = lambda: talking[0]

    async def run():
        task = asyncio.create_task(s.approvals.confirm(QUESTION))
        await asyncio.sleep(0.3)
        assert s.voice.spoken == [], "not over the user's words"
        talking[0] = False
        await asyncio.sleep(0.1)
        assert s.voice.spoken == [QUESTION]
        s.approvals.cancel()
        return await task

    assert asyncio.run(run()) is False


class AskingWorker:
    """Each turn asks before sending a mail, through the helpers' questions, like the connections server would."""

    name = "worker"

    def __init__(self, timeout_s: float):
        self.timeout_s = timeout_s
        self.questions: HelperQuestions | None = None
        self.prompts: list[str] = []
        self.decisions: list[str] = []

    async def reply(self, prompt, session_id, *, on_step=None, on_session=None, on_plan=None, scope=None) -> Reply:
        self.prompts.append(prompt)
        decision = await self.questions.approve("send", QUESTION)
        self.decisions.append(decision.answer)
        say = "Sent." if decision.allowed else "I'm waiting for your answer."
        return Reply(Emotion.HAPPY, say, Usage(10, 5, 0), "s1")


def parked_stack(monkeypatch) -> tuple[Stack, AskingWorker]:
    monkeypatch.setattr(orchestrator, "PARK_MARGIN_S", 0.1)
    worker = AskingWorker(timeout_s=0.3)  # the harness ends a turn after this: the question parks 0.1 s before
    s = Stack(harness=worker, confirm_timeout_s=0)
    worker.questions = HelperQuestions(s.approvals, lambda: s.tasks, screen=False)
    return s, worker


def test_a_helpers_question_parks_before_its_turn_must_end_and_a_yes_resumes_it(monkeypatch):
    s, worker = parked_stack(monkeypatch)

    async def run():
        helper = s.tasks.submit("write to Anna that dinner moves to Friday", title="Mail to Anna", screen=False,
                                user_asked=True)
        await asyncio.sleep(0.5)
        assert worker.decisions == ["parked"], "the worker was told to end its turn and wait"
        assert helper.status is HelperStatus.NEEDS_YOU and helper.active
        assert s.approvals.pending and not s.sink.of(ConfirmDone), "the question is still open"
        assert "waiting for the user's answer; it goes on after a yes" in s.tasks.board()
        assert "I'm waiting for your answer." not in s.bubbles(), "a parked turn's words aren't a result"
        [asked] = s.sink.of(Confirm)
        s.approvals.answer(asked.id, True)
        await s.tasks.idle()
        return helper

    helper = asyncio.run(run())
    assert worker.decisions == ["parked", "yes"], "the same question again is the yes already given: no second ask"
    assert len(s.sink.of(Confirm)) == 1
    assert QUESTION in worker.prompts[1] and "yes" in worker.prompts[1]
    assert helper.status is HelperStatus.DONE and helper.result == "Sent."


def test_a_no_to_a_parked_question_leaves_the_task_without_another_turn(monkeypatch):
    s, worker = parked_stack(monkeypatch)

    async def run():
        helper = s.tasks.submit("write to Anna", title="Mail to Anna", screen=False, user_asked=True)
        await asyncio.sleep(0.5)
        s.approvals.answer(s.sink.of(Confirm)[0].id, False)
        await s.tasks.idle()
        return helper

    helper = asyncio.run(run())
    assert len(worker.prompts) == 1 and helper.status is HelperStatus.STOPPED
    assert helper.result == "You said no, so I left it."


def test_stopping_a_parked_helper_takes_its_question_away(monkeypatch):
    s, worker = parked_stack(monkeypatch)

    async def run():
        s.tasks.submit("write to Anna", title="Mail to Anna", screen=False, user_asked=True)
        await asyncio.sleep(0.5)
        s.tasks.stop("all")
        await s.tasks.idle()
        await settle()

    asyncio.run(run())
    assert not s.approvals.pending and [d.answer for d in s.sink.of(ConfirmDone)] == ["no"]
    assert len(worker.prompts) == 1


def test_the_worker_hears_plainly_that_it_should_stop_and_wait():
    from milo.services.tool_requests import REFUSED as BRAIN_REFUSED
    from milo.transport.tool_client import REFUSED

    for words in (REFUSED["parked"], BRAIN_REFUSED["parked"]):
        assert "end your turn" in words and "Don't do it another way" in words


def test_the_yes_while_it_waited_covers_only_that_helpers_next_turn(monkeypatch):
    """The same words from another helper, or later from this one, ask again."""
    s, worker = parked_stack(monkeypatch)
    questions = worker.questions

    async def run():
        helper = s.tasks.submit("write to Anna", title="Mail to Anna", screen=False, user_asked=True)
        await asyncio.sleep(0.5)
        s.approvals.answer(s.sink.of(Confirm)[0].id, True)
        await s.tasks.idle()
        assert helper.granted == "", "used up in the turn after the yes"
        other = s.tasks.submit("write to Anna again", title="Mail again", screen=False, user_asked=True)
        await settle()
        return other

    asyncio.run(run())
    assert worker.decisions[:2] == ["parked", "yes"] and len(s.sink.of(Confirm)) == 2, "the second helper asked"
    del questions


def test_a_money_question_is_never_let_through_by_an_earlier_yes():
    from milo.services.helpers import Helper

    class OneHelper:
        """The orchestrator as HelperQuestions sees it, with one helper at work."""

        def __init__(self, helper):
            self.helper = helper

        def asking(self, *, screen):
            return self.helper

        def answered(self, helper):
            pass

        def careful(self, *, screen):
            return False

        def question_wait(self, helper):
            return None

    s = Stack(confirm_timeout_s=0)
    helper = Helper("h1", 1, "Tickets", "buy the tickets", False, 0.0, status=HelperStatus.WORKING,
                    granted="Buy 2 tickets for 40 €?")
    questions = HelperQuestions(s.approvals, lambda: OneHelper(helper), screen=False)

    async def run():
        task = asyncio.create_task(questions.approve("buy", "Buy 2 tickets for 40 €?"))
        await settle()
        s.approvals.cancel()
        return await task

    assert not asyncio.run(run()).allowed
    assert s.sink.of(Confirm)[-1].money, "asked again, as a money question that only a click answers"
