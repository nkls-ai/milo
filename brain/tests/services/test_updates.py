"""Progress updates: milestone rules, the quiet, bubble and chatty modes, and settings that apply live."""

import asyncio
import os

import pytest

from milo.config import Config
from milo.core.events import Bubble
from milo.core.registry import ConfigError
from milo.core.types import Step, StepStatus
from milo.services.helpers import Helper
from milo.services.updates import LiveSettings, Milestones, UpdateMode, Updates
from tests.fakes import FakeClock, FakeLiveModel, RecordingSink, ScriptedHarness, WorkerScript
from tests.services.stack import Stack, settle

R = StepStatus.RUNNING


def step(id: str, title: str, kind: str = "read") -> Step:
    return Step(id, kind, title, "", R)


def helper(started_at: float = 1000.0) -> Helper:
    return Helper("h1", 1, "Budget table", "make a budget table", True, started_at, started_at=started_at)


# ---- milestones


def test_a_new_app_the_first_edit_and_the_first_web_step_are_milestones():
    m, h = Milestones(first_after_s=0, gap_s=0), helper()
    found = [m.step(h, s, 1010) for s in (
        step("1", "Looking in your Documents folder"), step("2", "Opening Microsoft Excel", "app"),
        step("3", "Reading budget.xlsx"), step("4", "Typing “Monday” in Excel", "app"),
        step("5", "Editing budget.xlsx", "edit"), step("6", "Editing notes.md", "edit"),
        step("7", "Searching the web for “prices”", "web"), step("8", "Opening Safari", "app"))]
    assert found == [None, "Opening Microsoft Excel", None, None, "Editing budget.xlsx", None,
                     "Searching the web for “prices”", "Opening Safari"]


def test_milestones_wait_for_the_start_and_keep_their_distance():
    m, h = Milestones(first_after_s=5, gap_s=20), helper(started_at=1000)
    assert m.step(h, step("1", "Opening Excel", "app"), 1002) is None, "too soon after the acknowledgement"
    assert m.step(h, step("2", "Editing a.xlsx", "edit"), 1010) == "Editing a.xlsx"
    assert m.step(h, step("3", "Searching the web", "web"), 1015) is None, "too soon after the last one"
    assert m.step(h, step("4", "Opening Safari", "app"), 1031) == "Opening Safari"


def test_halfway_through_the_plan_is_a_milestone_once():
    m, h = Milestones(first_after_s=0, gap_s=0), helper()
    assert [m.plan(h, d, 4, 1010) for d in (1, 2, 3, 4)] == [None, "Halfway there, 2 of 4 done", None, None]
    assert Milestones(first_after_s=0, gap_s=0).plan(h, 1, 2, 1010) is None, "two items are no plan to report on"


# ---- modes


def updates(mode: UpdateMode, *, busy: bool = False, speak=None):
    sink, clock = RecordingSink(), FakeClock()
    return Updates(sink, lambda: mode, clock, busy=lambda: busy, speak=speak), sink, clock


def test_quiet_says_and_shows_nothing():
    u, sink, _ = updates(UpdateMode.QUIET, speak=lambda text: pytest.fail("quiet never speaks"))
    u.milestone(helper(), "Opening Excel")
    assert sink.events == []


def test_bubble_shows_a_short_note_and_never_too_often():
    u, sink, clock = updates(UpdateMode.BUBBLE, speak=lambda text: pytest.fail("bubble never speaks"))
    u.milestone(helper(), "Opening Excel")
    u.milestone(helper(), "Editing budget.xlsx")
    clock.advance(seconds=7)
    u.milestone(helper(), "Searching the web")
    assert sink.events == [Bubble("Budget table: Opening Excel"), Bubble("Budget table: Searching the web")]


def test_nothing_covers_an_answer_a_recording_or_a_question():
    u, sink, _ = updates(UpdateMode.CHATTY, busy=True, speak=lambda text: pytest.fail("busy"))
    u.milestone(helper(), "Opening Excel")
    assert sink.events == []


def test_chatty_speaks_at_most_every_so_often_and_shows_a_note_in_between():
    said: list[str] = []
    u, sink, clock = updates(UpdateMode.CHATTY, speak=lambda text: said.append(text) or True)
    u.milestone(helper(), "Opening Excel")
    clock.advance(seconds=10)
    u.milestone(helper(), "Editing budget.xlsx")
    clock.advance(seconds=40)
    u.milestone(helper(), "Searching the web")
    assert said == ["Budget table: Opening Excel", "Budget table: Searching the web"]
    assert sink.events == [Bubble("Budget table: Editing budget.xlsx")]


def test_chatty_hands_the_talker_the_plain_words_and_the_bubble_the_full_step():
    said: list[str] = []
    u, sink, _ = updates(UpdateMode.CHATTY, speak=lambda text: said.append(text) or True)
    u.milestone(helper(), "Searching the web for “cheap flights”", "looking things up online")
    assert said == ["Budget table: looking things up online"]


def test_chatty_falls_back_to_a_note_when_the_talker_is_not_free():
    u, sink, _ = updates(UpdateMode.CHATTY, speak=lambda text: False)
    u.milestone(helper(), "Opening Excel")
    assert sink.events == [Bubble("Budget table: Opening Excel")]


def test_chatty_end_to_end_the_talker_phrases_the_milestone_without_tags(fake_installed_apps):
    gate = asyncio.Event()
    s = Stack(model=FakeLiveModel(["[happy] Excel is open, filling in the days now. <task>sneaky</task>"]),
              harness=ScriptedHarness(WorkerScript(("sleep", 0.001), step("1", "Opening Safari", "app"), gate,
                                                   "Done.")))
    s.tasks.updates = Updates(s.ui, lambda: UpdateMode.CHATTY, s.clock, speak=s.live_talk.speak_update)
    s.tasks._milestones = Milestones(first_after_s=0, gap_s=0)

    async def run():
        s.tasks.submit("make a budget table in Excel", title="Budget table")
        await asyncio.sleep(0.01)
        await settle()
        gate.set()
        await s.tasks.idle()
        await settle()

    asyncio.run(run())
    assert "<helper_update>Budget table: working in Safari</helper_update>" in s.model.turns[0]
    assert s.voice.spoken == ["Excel is open, filling in the days now.", "Done."]
    assert len(s.tasks.helpers) == 1, "tags in a spoken update start nothing"


# ---- settings


def test_updates_and_max_helpers_are_checked():
    config = Config.parse('[chat]\nupdates = "chatty"\n[harness]\nuse = "codex"\nmax_helpers = 2\n')
    assert (config.chat.updates, config.harness.max_helpers) == ("chatty", 2)
    assert (Config.parse("").chat.updates, Config.parse("").harness.max_helpers) == ("bubble", 3)
    with pytest.raises(ConfigError, match="updates must be one of quiet, bubble, chatty"):
        Config.parse('[chat]\nupdates = "loud"\n')
    for bad in ("0", "9", "1.5", "true"):
        with pytest.raises(ConfigError, match="max_helpers"):
            Config.parse(f"[harness]\nmax_helpers = {bad}\n")


def test_live_settings_follow_config_toml_without_a_restart(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[chat]\nupdates = "bubble"\n', encoding="utf-8")
    now = [0.0]

    def parse(text: str):
        c = Config.parse(text)
        return c.chat.updates, c.harness.max_helpers

    live = LiveSettings(path, parse, "bubble", 3, check_s=2, monotonic=lambda: now[0])
    path.write_text('[chat]\nupdates = "quiet"\n[harness]\nmax_helpers = 1\n', encoding="utf-8")
    os.utime(path, (1, 1))
    assert live.updates() is UpdateMode.BUBBLE, "not checked again yet"
    now[0] = 3
    assert (live.updates(), live.max_helpers()) == (UpdateMode.QUIET, 1)
    path.write_text('[chat]\nupdates = "very loud"\n', encoding="utf-8")
    os.utime(path, (2, 2))
    now[0] = 6
    assert live.updates() is UpdateMode.QUIET, "a broken file keeps the last good value"


def test_a_change_from_the_settings_window_applies_at_once(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[chat]\nupdates = "bubble"\n', encoding="utf-8")
    live = LiveSettings(path, lambda text: ("bubble", 3), "bubble", 3, check_s=2, monotonic=lambda: 0.0)
    path.write_text('[chat]\nupdates = "chatty"\n', encoding="utf-8")
    os.utime(path, (5, 5))
    live.use("chatty", 2)
    assert (live.updates(), live.max_helpers()) == (UpdateMode.CHATTY, 2)
