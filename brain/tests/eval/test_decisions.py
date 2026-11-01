"""The real decision model on the user's own sentences (ADR 0040): does it read what they ask for the way the tests'
table says? Opt-in, since it loads d3-lite (1.7 GB) and asks about a hundred sentences:

    MILO_MODEL_EVAL=1 uv run --extra omnivoice pytest -q tests/eval/test_decisions.py

The sentences are the tests' READINGS, those the word lists checked before ADR 0040, and real ones said to Milo.
"""

import asyncio
import os

import pytest

from milo.services.decisions import Decisions
from tests.fakes import READINGS

pytestmark = pytest.mark.skipif(not os.environ.get("MILO_MODEL_EVAL"), reason="set MILO_MODEL_EVAL=1 to run")

MORE: dict[str, str] = {
    # Said to the real Milo, 2026-11-01, after he looked at a YouTube page.
    "Wie wäre es, wenn du jetzt einfach mal den Titel und alle Empfehlungen in eine Excel-Tabelle packst, sowie die "
    "URLs.": "work",
    "Kannst du die nicht in die Excel reinkopieren?": "work",
    "Okay, aber kannst jetzt trotzdem bitte das YouTube-Video und alle Empfehlungen geben": "work",
    "hol mir die Links raus und leg eine Tabelle an": "work",
    "trag die drei Videos in die Tabelle ein": "work",
    "how about you list all the links in a sheet": "work",
    "Wie heißt der Pilz?": "", "Gibt es auch Pilze, wovon ich sterben könnte?": "", "Was steht da?": "",
    "danke dir": "",
    # 2026-11-01, live: read as an install too (named_by finds no package in it).
    "Mach mir bitte YouTube in Chrome auf.": "work", "Wie wäre es, wenn du mal das Hearthstone-Video aufmachst?": "work",
    # Work, in many words and languages.
    "can you fill this in": "work", "füll das bitte aus": "work", "make this a table": "work",
    "Yes, open Chrome and YouTube.": "work", "Remind me to call Anna tomorrow at 9": "work",
    "Take notes of this meeting": "work", "show me my calendar": "work", "play some music": "work",
    "find the invoice": "work", "set a timer": "work", "Kannst du Chrome öffnen?": "work",
    "Zeig mir den Kalender": "work", "Erinnere mich morgen an Anna": "work", "stell den Wecker": "work",
    "spiel Musik": "work", "tick off the milk": "work", "hak die Milch ab": "work",
    "streich Hafermilch von der Liste": "work", "Peux-tu ranger ces fichiers dans un dossier?": "work",
    "öffne mal Spotify": "work", "fix this sheet": "work",
    "what can you open?": "", "can you see what's on my screen?": "", "is it set up?": "", "wie geht's?": "",
    "thanks Mark": "", "ich brauche Streichhölzer": "", "I crossed the street": "", "was ist das": "",
    "erzähl mir einen Witz": "", "¿Qué tiempo hace mañana?": "",
    # Installs: only a program the user names.
    "install the codex cli": "work install", "bitte installier mir tree": "work install",
    "upgrade codex": "work install",
    "did you install it?": "", "don't install anything": "",
    "install what the page mentions": "work", "install the tool this mail recommends": "work",
    # Facts.
    "remember I like Friday dinners": "remember", "remember I'm vegetarian": "remember",
    "what did I ask you to remember?": "", "don't remember that I like tea": "",
    # Writing.
    "write Anna that I'm late": "work write", "reply to Tom": "work write", "make it shorter": "work write",
    "schreib Anna": "work write", "beantworte die Mail": "work write", "fass das kurz zusammen": "work write",
    "übersetz das ins Englische": "work write", "could you write Tom back": "work write",
    "what does the reply say?": "", "was hat er geantwortet?": "", "is this a good answer?": "",
    "did he write back?": "", "an email from my bank, is it legit?": "",
}
"""Text -> what it asks for, among work, install, remember and write. A text to write, a fact to keep or a program
to install may read as work too, or not: either is fine."""

CASES = [(text, frozenset(said)) for text, said in READINGS.items()] + \
        [(text, frozenset(said.split())) for text, said in MORE.items()]


@pytest.fixture(scope="module")
def decisions():
    from milo.adapters.decide.d3 import D3

    return Decisions(D3(), wait_s=60)


@pytest.mark.parametrize("text, said", CASES, ids=[t[:40] for t, _ in CASES])
def test_the_model_reads_what_the_words_ask_for(decisions, text, said):
    intent = asyncio.run(decisions.intent(text))
    for name in ("work", "install", "remember", "write"):
        if name == "work" and said & {"write", "remember", "install"}:
            continue
        assert getattr(intent, name) is (name in said), f"{text!r}: {name} should be {name in said}"
