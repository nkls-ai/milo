"""The eval's cases match docs/eval/tasks.md, and no check passes on a world Milo never touched."""

import re
from datetime import date
from pathlib import Path

from milo.eval.cases import CASES, Outcome
from milo.eval.runner import CONFIG, summary
from milo.eval.world import build, next_weekday, seed

TASKS_MD = Path(__file__).parents[3] / "docs" / "eval" / "tasks.md"
TODAY = date(2026, 10, 30)


def test_thirty_cases_and_the_doc_lists_the_same_ones():
    rows = re.findall(r"^\| (c\d\d) \| (.+?) \| (.+?) \| (\w+) \|$", TASKS_MD.read_text(), re.M)
    assert len(CASES) == 30 and len({c.id for c in CASES}) == 30
    assert [(c.id, c.say, c.expect, c.ability) for c in CASES] == rows


def test_doing_nothing_fails_every_case_except_refusing_money():
    for case in CASES:
        idle = Outcome(TODAY, build(TODAY), replies=["Sorry, I can't do that."])
        assert case.check(idle) is (case.id == "c29"), case.id


def test_a_worked_example_passes():
    [c01] = [c for c in CASES if c.id == "c01"]
    world = build(TODAY)
    thursday = next_weekday(TODAY, 3)
    world["events"].append({"id": "x", "title": "Doctor", "start": f"{thursday}T15:00", "end": f"{thursday}T16:00"})
    assert c01.check(Outcome(TODAY, world))


def test_the_world_seeds_readable_files(tmp_path):
    from milo.adapters.connect import _files

    world = seed(tmp_path, TODAY)
    bill = next(world.home.rglob("Stromrechnung 2026-09.pdf"))
    assert "84,20 EUR" in _files.text_of(bill)
    assert "heating" in _files.text_of(next(world.home.rglob("*.docx")))


def test_the_eval_config_keeps_the_worker_away_from_real_data():
    from milo.config import Config

    config = Config.parse(CONFIG.format(chat_model="m", worker_model="m") + '\n[ui]\n')
    assert config.pluggable("connections")[0] == "fake"
    assert {"Bash", "Read", "WebFetch"} <= set(config.pluggable("harness")[1]["disallowed_tools"])
    for section in ("stt", "tts", "audio"):
        assert config.pluggable(section)[0] == "none"
    assert config.heartbeat.enabled is False
    assert config.hands.enabled is False, "no milo-mac tools on the real screen"


def test_summary_counts_per_ability():
    from milo.eval.runner import Result

    results = [Result(CASES[0], True, 10.0, "", []), Result(CASES[5], False, 20.0, "", [])]
    assert summary(results) == "score 1/2, median 15.0s (calendar 1/1, reminders 0/1)"
