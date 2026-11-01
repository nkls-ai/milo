"""Typed questions about one text, answered by a small local decision model with a probability for every answer
(ADR 0040).

Milo asks them where a rule would otherwise be a list of words: did the user's own words ask for work, an install,
a fact kept, a text written? A list knows one language and the phrasings someone thought of; the model reads the
sentence. Helpers ask them too, through the `classify` tool, with classes of their own (folders for mail, kinds of
tickets).

A Decider is blocking and runs on its own single-thread executor, like STT and TTS (services/decisions.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class YesNo:
    """A yes-or-no question. Its answer is the probability of yes."""

    question: str


@dataclass(frozen=True)
class Choice:
    """One of a few options. Its answer is a probability for each option, summing to 1."""

    question: str
    options: Mapping[str, str]
    """Option name -> what it means, e.g. {"bills": "invoices, receipts, payments due"}."""


Question = YesNo | Choice
Answer = float | dict[str, float]


class Decider(Protocol):
    name: str

    def warm(self) -> None:
        """Load the model, so the first question isn't the slow one."""
        ...

    def decide(self, text: str, questions: Mapping[str, Question]) -> dict[str, Answer | None]:
        """Each question about `text`, answered. None for one the model couldn't answer (too long, malformed)."""
        ...
