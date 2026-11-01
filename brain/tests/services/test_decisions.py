"""The decision model's two jobs (ADR 0040): what the user's own words ask for, and the helpers' `classify`. The
model here is a table (tests/fakes.FakeDecider); tests/eval/test_decisions.py runs the real one."""

import asyncio
import time

import pytest

from milo.adapters.decide.d3 import _answer, _wire
from milo.core.decide import Choice, YesNo
from milo.services.decisions import Decisions, Intent
from tests.fakes import FakeDecider


def test_the_users_words_read_as_what_they_ask_for():
    decisions = Decisions(FakeDecider({"installier mir tree": frozenset({"work", "install"})}))
    assert asyncio.run(decisions.intent("installier mir tree")) == Intent(work=True, install=True)
    assert asyncio.run(decisions.intent("Was steht da?")) == Intent()


class Slow(FakeDecider):
    def decide(self, text, questions):
        time.sleep(0.3)
        return super().decide(text, questions)


class Broken(FakeDecider):
    def decide(self, text, questions):
        raise RuntimeError("out of memory")


@pytest.mark.parametrize("decisions", [
    Decisions(None),
    Decisions(Slow({"fix this": frozenset({"work"})}), wait_s=0.05),
    Decisions(Broken({"fix this": frozenset({"work"})})),
], ids=["no model", "too slow", "broken"])
def test_without_a_reading_in_time_nothing_counts_as_asked(decisions):
    """Then Milo asks first: the safe side."""
    assert asyncio.run(decisions.intent("fix this")) == Intent()


def test_classify_sorts_each_item_and_says_how_sure():
    class Mail(FakeDecider):
        def decide(self, text, questions):
            [q] = questions.values()
            assert isinstance(q, Choice) and q.question == "Which folder?"
            best = "bills" if "Rechnung" in text else "personal"
            return {k: {o: 0.9 if o == best else 0.1 for o in q.options} for k in questions}

    decisions = Decisions(Mail())
    sorted_ = asyncio.run(decisions.classify(["Telekom: Ihre Rechnung", "Mama: Sonntag Essen?"],
                                             {"bills": "invoices", "personal": "family"}, "Which folder?"))
    assert [(s["class"], s["confidence"]) for s in sorted_] == [("bills", 0.9), ("personal", 0.9)]
    assert sorted_[0]["probabilities"] == {"bills": 0.9, "personal": 0.1}


def test_classify_says_what_is_wrong_with_a_call():
    decisions = Decisions(FakeDecider())
    with pytest.raises(ValueError, match="between 2"):
        asyncio.run(decisions.classify(["x"], {"only": "one class"}))
    with pytest.raises(ValueError, match="At most"):
        asyncio.run(decisions.classify(["x"] * 201, {"a": "", "b": ""}))
    with pytest.raises(ValueError, match="no decision model"):
        asyncio.run(Decisions(None).classify(["x"], {"a": "", "b": ""}))


def test_d3_gets_its_own_question_shapes_and_an_error_is_no_answer():
    assert _wire(YesNo("Asked?")) == {"type": "noul", "instructions": "Asked?"}
    assert _wire(Choice("Which?", {"a": "first"})) == {"type": "choice", "instructions": "Which?",
                                                       "criteria": {"a": "first"}}
    assert _answer({"type": "noul", "noul": 0.8}) == 0.8
    assert _answer({"type": "choice", "choice": "a", "probabilities": {"a": 0.7, "b": 0.3}}) == {"a": 0.7, "b": 0.3}
    assert _answer({"type": "noul", "error": "max_length_exceeded"}) is None


def test_the_talk_key_wakes_a_model_left_idle():
    """After a night idle the first readings missed `wait_s`: the key press pages it in while the user speaks."""
    from milo.services import decisions as module

    class Counting(FakeDecider):
        warmed = 0

        def warm(self):
            self.warmed += 1

    async def press_twice(decisions):
        decisions.wake()
        decisions.wake()  # just woken: not again
        await asyncio.sleep(0.05)

    decider = Counting()
    decisions = Decisions(decider)
    asyncio.run(press_twice(decisions))
    assert decider.warmed == 0  # it was just loaded
    decisions._used -= module.IDLE_S + 1
    asyncio.run(press_twice(decisions))
    assert decider.warmed == 1
