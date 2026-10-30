"""The recall eval: about 50 scripted days of conversations, tasks and facts, then questions. Scores whether each
answer's memory made it into the turn, what that cost in tokens, and how long recall took.

    uv run python -m milo.memory.recall_eval                     # the hashing embedder, like CI
    uv run python -m milo.memory.recall_eval --embedder mlx_e5   # the real model (downloads 470 MB once)
    uv run python -m milo.memory.recall_eval --scale 20          # thousands of extra episodes, for latency

Everything happens in a temporary folder; the user's ~/Milo is never touched.
"""

from __future__ import annotations

import argparse
import random
import statistics
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from milo.core.memory import Episode, Fact, TurnContext, new_id
from milo.core.ports import Embedder

from .episodes import JsonlEpisodeLog
from .facts import JsonlFactStore
from .index import SqliteMemoryIndex
from .recall import HybridRecaller, RecallTuning

NOW = datetime(2026, 10, 30, 18, 0)  # a Friday evening, the end of day 50
DAYS = 50


@dataclass(frozen=True)
class Question:
    text: str
    want: tuple[str, ...]
    """Keys of the stories any of which answers it. Empty: nothing beyond the always-on facts should come."""
    never: tuple[str, ...] = ()
    """Keys that must not come back (retired or replaced facts)."""
    app: str | None = None


@dataclass
class World:
    facts: dict[str, Fact] = field(default_factory=dict)
    episodes: dict[str, Episode] = field(default_factory=dict)


def _said(user: str, milo: str) -> str:
    return f"The user said: “{user}” Milo answered: “{milo}”"


def _ago(days: float, hour: int = 10) -> datetime:
    return (NOW - timedelta(days=days)).replace(hour=hour, minute=random.randint(0, 59))


# key -> (days ago, kind, text, trusted, apps). Facts have kind "fact:<topic>".
STORIES: dict[str, tuple[float, str, str, bool, tuple[str, ...]]] = {
    "name": (49, "fact:basics", "The user's name is Niklas.", True, ()),
    "language": (49, "fact:basics", "The user speaks German and English.", True, ()),
    "anna": (44, "fact:people", "Anna is the user's sister. Her birthday is March 3.", True, ()),
    "anna_hamburg": (40, "fact:people", "Anna lives in Hamburg.", True, ()),
    "anna_berlin": (6, "fact:people", "Anna lives in Berlin now.", True, ()),
    "lena": (38, "fact:people", "Lena is the user's partner.", True, ()),
    "mia": (37, "fact:people", "Mia is the user's daughter.", True, ()),
    "mia_training": (30, "fact:routines", "Mia has football training on Thursdays at 5 pm.", True, ()),
    "mother": (29, "fact:routines", "The user calls his mother on Sundays.", True, ()),
    "tea": (28, "fact:preferences", "The user drinks tea, not coffee, in the afternoon.", True, ()),
    "work": (47, "fact:work", "The user works at Nordwind GmbH as a product designer.", True, ()),
    "penicillin": (25, "fact:learned", "The user is allergic to penicillin.", True, ()),
    "gym": (22, "fact:learned", "The user's gym is FitX; the membership renews in February.", True, ()),
    "old_phone": (45, "fact:learned", "The user's old phone number ended in 4471.", True, ()),
    "dentist": (9, "conversation", _said("Can you find me a dentist appointment with Dr. Weber next Tuesday?",
                                         "I put Dr. Weber on Tuesday at 2 pm in your calendar."), True, ("Calendar",)),
    "excel": (12, "task", "Task: make a budget table in Excel with a total row. It failed: Milo wasn't allowed to "
                          "control Microsoft Excel (Accessibility was off).", False, ("Microsoft Excel",)),
    "electricity": (18, "task", "Task: find the electricity bill from September. Result: Stadtwerke, 84,20 EUR, "
                                "paid on October 12.", False, ("Finder",)),
    "lisbon": (15, "conversation", _said("Book me the flight to Lisbon on November 14, window seat please.",
                                         "Done: TAP on November 14, seat 12A."), True, ("Safari",)),
    "jonas_book": (20, "conversation", _said("Jonas recommended a book, Thinking in Systems, remind me to buy it.",
                                             "I'll remind you on Saturday."), True, ()),
    "photos": (1, "task", "Task: rename the photos from the hike in Pictures by date. Result: renamed 40 photos.",
               False, ("Finder",)),
    "landlord": (11, "task", "Task: write a draft to the landlord Mr. Schulz about the broken heating. Result: the "
                             "draft is ready in Mail.", False, ("Mail",)),
    "car": (55, "conversation", _said("Book the car inspection at ATU, January 12 is fine.",
                                      "Booked: ATU, January 12 at 8 am."), True, ()),
    "printer": (27, "conversation", _said("Wie verbinde ich den Drucker im Büro?",
                                          "Über Systemeinstellungen, Drucker, plus, dann den Brother im WLAN."),
                True, ("System Settings",)),
    "jonas_meeting": (8, "meeting", "Meeting with Jonas about the roadmap: they decided to ship memory before "
                                    "meeting notes.", True, ("Zoom",)),
    "soup": (4, "conversation", _said("Give me a recipe for pumpkin soup.",
                                      "Roast the pumpkin, then blend it with stock and ginger."), True, ()),
    "dinner": (2, "conversation", _said("Book a table at Trattoria Da Enzo for Saturday, 8 pm, four people.",
                                        "Booked for four on Saturday at 8."), True, ()),
    "plants": (33, "conversation", _said("Remind me to water the plants every Wednesday.",
                                         "I'll remind you on Wednesdays at 6 pm."), True, ()),
}
REPLACED = {"anna_hamburg": "anna_berlin"}
RETIRED = ("old_phone",)

QUESTIONS = (
    Question("When is Anna's birthday?", ("anna",)),
    Question("Wann hat Anna Geburtstag?", ("anna",)),
    Question("What did I ask you about the dentist last week?", ("dentist",)),
    Question("Wann war nochmal der Zahnarzttermin?", ("dentist",)),
    Question("What was the problem with the Excel table?", ("excel",), app="Microsoft Excel"),
    Question("Who is Lena?", ("lena",)),
    Question("How much was the electricity bill?", ("electricity",)),
    Question("Wie hoch war die Stromrechnung?", ("electricity",)),
    Question("When do I usually call my mom?", ("mother",)),
    Question("What do I like to drink in the afternoon?", ("tea",)),
    Question("When do I fly to Lisbon?", ("lisbon",)),
    Question("Where do I work?", ("work",)),
    Question("Which book did Jonas recommend?", ("jonas_book",)),
    Question("Wann hat Mia Fußballtraining?", ("mia_training",)),
    Question("What did we do yesterday?", ("photos",)),
    Question("Do I have any allergies to medicine?", ("penicillin",)),
    Question("Did I write to the landlord about the heating?", ("landlord",)),
    Question("Where does Anna live?", ("anna_berlin",), never=("anna_hamburg",)),
    Question("What was my old phone number?", (), never=("old_phone",)),
    Question("When is the car inspection?", ("car",)),
    Question("How did I connect the office printer?", ("printer",)),
    Question("Wann verlängert sich mein Fitnessstudio-Vertrag?", ("gym",)),
    Question("What did we decide with Jonas about the roadmap?", ("jonas_meeting",)),
    Question("What recipe did I ask for on Monday?", ("soup",)),
    Question("Where did I book dinner for Saturday?", ("dinner",)),
    Question("What's my daughter's name?", ("mia",)),
    Question("What did I want to be reminded of on Wednesdays?", ("plants",)),
    Question("Tell me a joke.", ()),
    Question("Wie spät ist es?", ()),
    Question("Thanks, that's all.", ()),
)

SMALL_TALK = [
    ("How's the weather today?", "Sunny and 14 degrees."), ("What time is it in Tokyo?", "It's 2 in the morning."),
    ("Play some jazz.", "I can't play music yet."), ("How do you spell necessary?", "N-E-C-E-S-S-A-R-Y."),
    ("Wie ist das Wetter morgen?", "Regnerisch, 9 Grad."), ("Was ist 17 mal 23?", "391."),
    ("Convert 30 miles to kilometers.", "About 48 kilometers."), ("Give me a word for happy.", "Cheerful."),
    ("Wie viele Tage hat der Februar?", "28, im Schaltjahr 29."), ("What's the capital of Canada?", "Ottawa."),
    ("Set a timer for ten minutes.", "Timer set for ten minutes."), ("Who wrote Faust?", "Goethe."),
]
TASKS = [
    "summarize the article about {x} in Safari", "find the PDF about {x} in Downloads", "make a note about {x}",
    "look up opening hours of the {x} shop", "draft an email to the team about {x}", "check the calendar for {x}",
]
TOPICS_X = ["solar panels", "the Q3 report", "bike repair", "tax forms", "the design review", "a birthday present",
            "garden chairs", "the release notes", "train tickets", "the onboarding doc", "kitchen lamps", "a new laptop"]
NOISE_FACTS = ["The user likes jazz.", "The user has a cat called Pixel.", "The user bikes to work in summer.",
               "The user's favourite colour is green.", "The user reads before bed.", "The user dislikes cilantro."]


def build_world(scale: int = 1, seed: int = 7) -> World:
    random.seed(seed)
    world = World()
    for key, (days, kind, text, trusted, apps) in STORIES.items():
        at = _ago(days)
        if kind.startswith("fact:"):
            replaces = next((world.facts[old].id for old, new in REPLACED.items() if new == key and old in world.facts),
                            None)
            world.facts[key] = Fact(new_id(at), text, kind[5:], at, "eval", replaces=replaces)
        else:
            world.episodes[key] = Episode(new_id(at), at, kind, text, apps=apps, trusted=trusted)
    for i, text in enumerate(NOISE_FACTS):
        at = _ago(40 - i * 5)
        world.facts[f"noise_fact_{i}"] = Fact(new_id(at), text, "learned", at, "eval")
    n = 0
    for day in range(DAYS * scale):
        for _ in range(random.randint(4, 9)):
            at = _ago(day % (DAYS + 30) + random.random(), random.randint(8, 22))
            if random.random() < 0.65:
                user, milo = random.choice(SMALL_TALK)
                episode = Episode(new_id(at), at, "conversation", _said(user, milo))
            else:
                task = random.choice(TASKS).format(x=random.choice(TOPICS_X))
                episode = Episode(new_id(at), at, "task", f"Task: {task}. Result: done.", trusted=False)
            world.episodes[f"noise_{n}"] = episode
            n += 1
    return world


@dataclass
class Score:
    hits: int = 0
    asked: int = 0
    tokens: list[int] = field(default_factory=list)
    millis: list[float] = field(default_factory=list)
    embed_millis: list[float] = field(default_factory=list)
    misses: list[str] = field(default_factory=list)
    items: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits / self.asked if self.asked else 0.0

    def report(self) -> str:
        return (f"{self.hits}/{self.asked} hits ({self.hit_rate:.0%}), {self.items} items in memory, "
                f"{statistics.mean(self.tokens):.0f} tokens per turn on average (max {max(self.tokens)}), "
                f"embedding the turn {_spread(self.embed_millis)}, the rest of the recall {_spread(self.millis)}")


def _spread(millis: list[float]) -> str:
    ms = sorted(millis)
    return f"{statistics.median(ms):.1f} ms median, {ms[max(0, int(len(ms) * 0.95) - 1)]:.1f} ms p95"


def run(embedder: Embedder, *, budget: int = 800, scale: int = 1, folder: Path | None = None,
        vectors: str = "numpy") -> Score:
    with tempfile.TemporaryDirectory(prefix="milo-recall-eval-") as tmp:
        root = folder or Path(tmp)
        world = build_world(scale)
        facts = JsonlFactStore(root / "facts.jsonl")
        episodes = JsonlEpisodeLog(root / "episodes")
        for fact in world.facts.values():
            facts.add(fact)
        for key in RETIRED:
            facts.retire(world.facts[key].id, "the user forgot it")
        for episode in world.episodes.values():
            episodes.append(episode)
        index = SqliteMemoryIndex(root / "memory.sqlite", embedder, facts, episodes, vectors=vectors)
        index.refresh()
        recaller = HybridRecaller(index, facts, RecallTuning(min_similarity=embedder.relevant_similarity))
        ids = {key: thing.id for key, thing in [*world.facts.items(), *world.episodes.items()]}
        score = Score(items=index.count())
        recaller.recall("warm up", TurnContext(NOW), budget)
        for q in QUESTIONS:
            started = time.perf_counter()
            index._query_vector(q.text)  # timed apart: the recall below finds it cached
            score.embed_millis.append((time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            recall = recaller.recall(q.text, TurnContext(NOW, q.app), budget)
            score.millis.append((time.perf_counter() - started) * 1000)
            score.tokens.append(recall.tokens)
            got = recall.ids
            always = {f.id for f in facts.current() if f.always_on}
            ok = (any(ids[k] in got for k in q.want) if q.want else not (got - always))
            ok = ok and not any(ids[k] in got for k in q.never)
            score.asked += 1
            score.hits += ok
            if not ok:
                score.misses.append(q.text)
        index.close()
        return score


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    args.add_argument("--embedder", default="hash", help="hash (default) or mlx_e5")
    args.add_argument("--budget", type=int, default=800)
    args.add_argument("--scale", type=int, default=1, help="days of noise times this, for latency on a big store")
    args.add_argument("--vectors", default="numpy", help="numpy or sqlite-vec")
    opts = args.parse_args(argv)
    from milo import adapters
    from milo.core.clock import SystemClock
    from milo.core.registry import EMBEDDERS, AdapterContext

    adapters.load_builtin()
    tmp = Path(tempfile.gettempdir())
    embedder = EMBEDDERS.create(opts.embedder, {}, AdapterContext(tmp, tmp, SystemClock()))
    embedder.warm()
    score = run(embedder, budget=opts.budget, scale=opts.scale, vectors=opts.vectors)
    print(f"{opts.embedder}: {score.report()}")
    for miss in score.misses:
        print(f"  missed: {miss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
