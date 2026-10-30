"""The heartbeat must be useful while costing nothing. These tests pin the cost, config and persistence."""

import json
from datetime import date, datetime, timedelta

import pytest

from milo.core.ports import LlmBudget, ProactiveEngine, ProactiveRule
from milo.core.registry import AdapterContext, ConfigError
from milo.memory.reminders import MarkdownReminders, parse
from milo.memory.workspace import Workspace
from milo.proactive import build_engine
from milo.proactive.budget import DailyBudget
from milo.proactive.rate_limit import RateLimiter
from tests.fakes import FakeClock, FakeHarness, ListReminders

from .helpers import AM, PM, default_section, engine, sig


def test_engine_and_rules_satisfy_the_ports(tmp_path):
    hb = engine(tmp_path)
    assert isinstance(hb, ProactiveEngine)
    assert isinstance(hb.budget, LlmBudget)
    assert all(isinstance(r, ProactiveRule) for r in hb.rules)
    assert [r.name for r in hb.rules] == ["reminders", "morning", "late_night", "welcome_back", "focus_break"]
    assert hb.tick_s == 30


def _user_day(t: datetime) -> tuple[float, str | None]:
    """A plausible weekday: asleep, long coding stretches, lunch, a meeting, a late evening."""
    h = t.hour + t.minute / 60
    if h < 1.5 or 2 <= h < 7.5:
        return 3600, None
    if 12 <= h < 13 or 18 <= h < 20:
        return 1800, "Safari"
    if 15 <= h < 16:
        return 10, "zoom.us"
    return 10, ("Xcode" if h < 15 or h >= 20 else "Safari")


def test_a_simulated_day_costs_zero_harness_calls(tmp_path):
    """24 h at tick_s=30 with the shipped [heartbeat] table, driven like the heartbeat runner."""
    home = tmp_path / "Milo"
    ws = Workspace(home)
    ws.ensure()
    ws.reminders_path.write_text("- [ ] 2026-10-29 10:00 Standup\n- [ ] 2026-10-29 15:30 Ask about budget\n")
    section = default_section()
    ctx = AdapterContext(home=home, state_dir=ws.state_dir, clock=FakeClock())
    hb = build_engine(section, ctx, MarkdownReminders(ws.reminders_path))
    assert hb.tick_s == 30
    harness = FakeHarness()
    spoken_by_hour: dict[int, int] = {}
    rules_seen = set()
    t = datetime(2026, 10, 29, 0, 0)
    while t < datetime(2026, 10, 30, 0, 0):
        idle_s, app = _user_day(t)
        for n in hb.tick(sig(t, idle_s=idle_s, app=app)):
            rules_seen.add(n.rule)
            if n.llm_prompt and hb.budget.allow(t.date()):
                hb.budget.spend(t.date())
                harness.calls.append((n.llm_prompt, None))
            if n.speak and n.rule != "reminders":
                spoken_by_hour[t.hour] = spoken_by_hour.get(t.hour, 0) + 1
        t += timedelta(seconds=hb.tick_s)
    assert harness.calls == []
    assert max(spoken_by_hour.values()) <= section["max_nudges_per_hour"]
    assert {"reminders", "morning", "late_night", "focus_break", "welcome_back"} <= rules_seen
    assert json.loads(ws.heartbeat_state_path.read_text())["budget"] == {}


def test_state_survives_restart(tmp_path):
    assert [n.rule for n in engine(tmp_path).tick(sig(AM))] == ["morning"]
    restarted = engine(tmp_path)
    assert restarted.tick(sig(AM + timedelta(minutes=5))) == []
    assert [n.rule for n in engine(tmp_path).tick(sig(AM + timedelta(days=1)))] == ["morning"]


def test_fired_reminders_survive_restart(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-29 13:00 Stretch\n"))
    assert len(engine(tmp_path, reminders).tick(sig(PM))) == 1
    assert engine(tmp_path, reminders).tick(sig(PM + timedelta(minutes=1))) == []
    saved = json.loads((tmp_path / "state" / "heartbeat.json").read_text())
    assert set(saved) == {"rules", "budget", "rate_limit"}


def test_budget_survives_restart(tmp_path):
    hb = engine(tmp_path, llm_calls_per_day=1)
    assert hb.budget.allow(PM.date())
    hb.budget.spend(PM.date())  # saved right away, not only on the next tick
    assert not engine(tmp_path, llm_calls_per_day=1).budget.allow(PM.date())


def test_state_file_is_at_the_workspace_path_and_written_atomically(tmp_path):
    hb = engine(tmp_path)
    hb.tick(sig(PM))
    assert Workspace(tmp_path).heartbeat_state_path.is_file()
    assert [p.name for p in (tmp_path / "state").iterdir()] == ["heartbeat.json"]


def test_corrupt_state_file_starts_fresh(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "heartbeat.json").write_text("{not json")
    assert [n.rule for n in engine(tmp_path).tick(sig(AM))] == ["morning"]
    (tmp_path / "state" / "heartbeat.json").write_text('{"rules": {"morning": "garbage"}, "budget": []}')
    assert [n.rule for n in engine(tmp_path).tick(sig(AM + timedelta(days=1)))] == ["morning"]


def test_unknown_rule_name_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="unknown heartbeat rule 'moring'"):
        engine(tmp_path, rules=["reminders", "moring"])


def test_unknown_key_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match=r"\[heartbeat\]: tick"):
        engine(tmp_path, tick=30)
    with pytest.raises(ConfigError, match=r"\[heartbeat.morning\]: afterhour"):
        engine(tmp_path, morning={"afterhour": 6})
    with pytest.raises(ConfigError, match=r"\[heartbeat.focusbreak\]"):
        engine(tmp_path, focusbreak={"after_min": 60})


def test_bad_values_are_config_errors(tmp_path):
    with pytest.raises(ConfigError, match="after_hour"):
        engine(tmp_path, morning={"after_hour": 13, "before_hour": 12})
    with pytest.raises(ConfigError, match="tick_s"):
        engine(tmp_path, tick_s=0)
    with pytest.raises(ConfigError, match="more than once"):
        engine(tmp_path, rules=["morning", "morning"])


def test_sub_table_for_a_disabled_rule_is_fine_and_enabled_is_ignored(tmp_path):
    hb = engine(tmp_path, rules=["reminders"], enabled=False)
    assert [r.name for r in hb.rules] == ["reminders"]
    assert hb.tick(sig(AM)) == []


def test_missing_sub_table_uses_defaults(tmp_path):
    section = {"rules": ["focus_break"]}
    ctx = AdapterContext(home=tmp_path, state_dir=tmp_path / "state", clock=FakeClock())
    hb = build_engine(section, ctx, ListReminders())
    assert hb.rules[0].options.after_min == 90
    assert not hb.budget.allow(PM.date())


def test_default_budget_never_allows_llm_calls():
    assert not DailyBudget(default_section()["llm_calls_per_day"], {}).allow(date(2026, 10, 29))


def test_budget_counts_per_day_and_keeps_only_today():
    state: dict = {}
    budget = DailyBudget(2, state)
    day = date(2026, 10, 29)
    budget.spend(day)
    budget.spend(day)
    assert not budget.allow(day)
    assert budget.allow(day + timedelta(days=1))
    budget.spend(day + timedelta(days=1))
    assert state == {"2026-10-30": 1}


def test_rate_limiter_gap_and_hourly_cap():
    state: dict = {}
    limiter = RateLimiter(timedelta(minutes=10), 2, state)
    assert limiter.take(PM)
    assert not limiter.take(PM + timedelta(minutes=5))
    assert limiter.take(PM + timedelta(minutes=10))
    assert not limiter.take(PM + timedelta(minutes=30))  # two in the last hour
    assert limiter.take(PM + timedelta(minutes=61))
    assert len(state["times"]) == 2


def test_rate_limit_survives_restart(tmp_path):
    opts = dict(max_nudges_per_hour=1, rules=["focus_break"], focus_break={"after_min": 10})
    hb = engine(tmp_path, **opts)
    first = [n for i in range(21) for n in hb.tick(sig(PM + timedelta(seconds=30 * i), app="Xcode"))]
    assert [n.rule for n in first] == ["focus_break"]
    restarted = engine(tmp_path, **opts)
    later = [n for i in range(21, 81) for n in restarted.tick(sig(PM + timedelta(seconds=30 * i), app="Xcode"))]
    assert later == []  # 40 minutes on, still within the hour of the first nudge
