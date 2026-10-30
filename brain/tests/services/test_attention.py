"""Attention: whether the user is busy, asked by name (review finding A2)."""

from milo.core.types import MiloState
from milo.services.attention import Attention


def test_each_question_combines_the_facts_it_names():
    facts = dict.fromkeys(("turn", "mic", "voice", "question", "helpers"), False)
    state = [MiloState.IDLE]
    a = Attention(lambda: state[0])
    a.attach(**{name: (lambda name=name: facts[name]) for name in facts})
    questions = ("in_conversation", "using_voice", "occupied", "at_work", "private", "user_speaking", "answering",
                 "recording")
    assert not any(getattr(a, q)() for q in questions), "idle: nobody is busy"

    def busy_with(fact: str) -> set[str]:
        facts[fact] = True
        try:
            return {q for q in questions if getattr(a, q)()}
        finally:
            facts[fact] = False

    assert busy_with("turn") == {"in_conversation", "using_voice", "occupied", "at_work", "answering"}
    assert busy_with("mic") == {"in_conversation", "using_voice", "occupied", "private", "user_speaking",
                                "recording"}
    assert busy_with("voice") == {"using_voice", "occupied", "private"}
    assert busy_with("question") == {"occupied"}
    assert busy_with("helpers") == {"at_work"}
    state[0] = MiloState.TRANSCRIBING
    assert {q for q in questions if getattr(a, q)()} == {"user_speaking"}, "its words are still being written"


def test_a_part_not_attached_yet_counts_as_idle():
    a = Attention()
    assert not a.in_conversation() and not a.user_speaking()
    a.attach(turn=lambda: True)
    assert a.in_conversation() and not a.private()
