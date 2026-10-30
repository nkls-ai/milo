"""Rule behavior through the engine, ported from the old heartbeat tests plus the new edges."""

from datetime import datetime, timedelta

from milo.core.types import Emotion, Reminder
from milo.memory.reminders import parse
from tests.fakes import ListReminders

from .helpers import AM, PM, engine, sig


def run(hb, start, minutes, step_s=30, **signal_kwargs):
    """Tick from `start` for `minutes`; returns (time, nudge) pairs."""
    out, t = [], start
    while t < start + timedelta(minutes=minutes):
        out += [(t, n) for n in hb.tick(sig(t, **signal_kwargs))]
        t += timedelta(seconds=step_s)
    return out


def test_morning_greeting_once_per_day(tmp_path):
    hb = engine(tmp_path)
    first = hb.tick(sig(AM))
    assert [(n.rule, n.speak, n.emotion) for n in first] == [("morning", True, Emotion.HAPPY)]
    assert first[0].text == "Good morning! I'm here if you need me."
    assert first[0].llm_prompt and "one short sentence" in first[0].llm_prompt
    assert hb.tick(sig(AM + timedelta(minutes=1))) == []
    assert [n.rule for n in hb.tick(sig(AM + timedelta(days=1)))] == ["morning"]


def test_morning_only_inside_its_window(tmp_path):
    hb = engine(tmp_path, rules=["morning"], morning={"after_hour": 7, "before_hour": 9})
    assert hb.tick(sig(AM.replace(hour=6, minute=59))) == []
    assert hb.tick(sig(AM.replace(hour=9))) == []
    hb2 = engine(tmp_path / "b", morning={"after_hour": 7, "before_hour": 9})
    assert [n.rule for n in hb2.tick(sig(AM.replace(hour=7)))] == ["morning"]


def test_morning_mentions_todays_reminders(tmp_path):
    reminders = ListReminders(
        Reminder("a", AM.replace(hour=15), "Call the dentist", False),
        Reminder("b", AM.replace(hour=10), "Standup", False),
        Reminder("c", AM.replace(hour=11), "done", True),
        Reminder("d", AM + timedelta(days=1), "tomorrow", False),
    )
    [greeting] = engine(tmp_path, reminders).tick(sig(AM))
    assert greeting.text == "Good morning! You have 2 reminders today, the first at 10:00."
    assert "10:00 Standup; 15:00 Call the dentist" in greeting.llm_prompt
    assert "tomorrow" not in greeting.llm_prompt


def test_no_voluntary_nudges_while_away_or_in_quiet_app(tmp_path):
    hb = engine(tmp_path)
    assert hb.tick(sig(AM, idle_s=900)) == []
    assert hb.tick(sig(AM, app="zoom.us")) == []


def test_focus_break_after_90_minutes_in_one_app(tmp_path):
    nudges = run(engine(tmp_path), PM, 100, idle_s=10, app="Xcode")
    assert [(n.rule, n.speak, n.emotion) for _, n in nudges] == [("focus_break", True, Emotion.CONCERNED)]
    assert nudges[0][1].text == "You've been in Xcode for 90 minutes. Stretch break?"


def test_switching_apps_resets_focus(tmp_path):
    """Three hours of work, switching app every 45 minutes, never reaches a 90 minute stretch."""
    hb, t, rules = engine(tmp_path), PM, []
    while t < PM + timedelta(hours=3):
        app = ("Xcode", "Safari")[int((t - PM).total_seconds() // 2700) % 2]
        rules += [n.rule for n in hb.tick(sig(t, idle_s=10, app=app))]
        t += timedelta(seconds=30)
    assert "focus_break" not in rules


def test_a_five_minute_pause_resets_focus(tmp_path):
    hb = engine(tmp_path)
    nudges = run(hb, PM, 60, idle_s=10, app="Xcode")
    # Six minutes away from the keyboard: idle_s climbs past 300 s.
    t = PM + timedelta(minutes=60)
    for i in range(12):
        nudges += [(t, n) for n in hb.tick(sig(t, idle_s=30 * (i + 1), app="Xcode"))]
        t += timedelta(seconds=30)
    nudges += run(hb, t, 60, idle_s=10, app="Xcode")
    assert [n.rule for _, n in nudges] == []


def test_welcome_back_is_bubble_only(tmp_path):
    hb = engine(tmp_path)
    hb.tick(sig(PM))
    nudges = hb.tick(sig(PM + timedelta(minutes=45)))
    assert [(n.rule, n.speak, n.emotion) for n in nudges] == [("welcome_back", False, Emotion.HAPPY)]
    assert hb.tick(sig(PM + timedelta(minutes=46))) == []


def test_time_in_a_quiet_app_is_not_time_away(tmp_path):
    hb = engine(tmp_path)
    hb.tick(sig(PM))
    run(hb, PM + timedelta(minutes=1), 45, app="zoom.us")
    assert hb.tick(sig(PM + timedelta(minutes=46))) == []


def test_idle_ticks_count_as_away(tmp_path):
    hb = engine(tmp_path, welcome_back={"away_min": 10})
    hb.tick(sig(PM))
    assert run(hb, PM + timedelta(minutes=1), 15, idle_s=600) == []
    assert [n.rule for n in hb.tick(sig(PM + timedelta(minutes=16)))] == ["welcome_back"]


def test_late_night_once_per_night_bubble_only(tmp_path):
    hb = engine(tmp_path, rules=["late_night"])
    night = datetime(2026, 10, 30, 1, 30)
    assert hb.tick(sig(night - timedelta(hours=1))) == []  # 00:30, outside 1..5
    nudges = hb.tick(sig(night))
    assert [(n.rule, n.speak, n.emotion) for n in nudges] == [("late_night", False, Emotion.SLEEPY)]
    assert hb.tick(sig(night + timedelta(hours=2))) == []
    assert [n.rule for n in hb.tick(sig(night + timedelta(days=1)))] == ["late_night"]


def test_late_night_window_can_wrap_midnight(tmp_path):
    hb = engine(tmp_path, rules=["late_night"], late_night={"from_hour": 23, "until_hour": 4})
    assert [n.rule for n in hb.tick(sig(datetime(2026, 10, 29, 23, 15)))] == ["late_night"]
    assert hb.tick(sig(datetime(2026, 10, 30, 2, 0))) == []  # same night
    assert hb.tick(sig(datetime(2026, 10, 30, 4, 0))) == []  # outside
    assert [n.rule for n in hb.tick(sig(datetime(2026, 10, 30, 23, 0)))] == ["late_night"]


def test_precedence_one_voluntary_nudge_per_tick(tmp_path):
    hb = engine(tmp_path)
    assert [n.rule for n in hb.tick(sig(datetime(2026, 10, 29, 4, 30)))] == ["late_night"]
    # Back after 90 minutes away in the morning: morning wins over welcome_back on that tick.
    assert [n.rule for n in hb.tick(sig(datetime(2026, 10, 29, 6, 0)))] == ["morning"]
    assert hb.tick(sig(datetime(2026, 10, 29, 6, 1))) == []


def test_reminders_fire_once_even_in_quiet_apps(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-29 09:00 Call the dentist\n- [x] 2026-10-29 09:00 done already\n"))
    hb = engine(tmp_path, reminders)
    assert hb.tick(sig(AM.replace(hour=8, minute=59), app="zoom.us")) == []
    fired = hb.tick(sig(AM.replace(hour=9), app="zoom.us"))
    assert [(n.rule, n.text, n.speak, n.emotion) for n in fired] == [
        ("reminders", "Reminder: Call the dentist", False, Emotion.EXCITED)]
    assert hb.tick(sig(AM.replace(hour=9, minute=1), app="zoom.us")) == []


def test_reminders_speak_outside_quiet_apps_even_when_away(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-29 13:00 Stretch\n"))
    fired = engine(tmp_path, reminders).tick(sig(PM, idle_s=3600))
    assert [(n.text, n.speak) for n in fired] == [("Reminder: Stretch", True)]


def test_late_reminder_says_when_it_was_due(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-29 12:50 Lunch\n"))
    fired = engine(tmp_path, reminders).tick(sig(PM, idle_s=3600))
    assert [n.text for n in fired] == ["Reminder from 12:50: Lunch"]


def test_very_old_reminders_are_dropped_silently(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-27 09:00 ancient\n"))
    hb = engine(tmp_path, reminders)
    assert hb.tick(sig(AM, idle_s=900, app=None)) == []
    assert hb.rules[0].state["fired"] == [reminders.items[0].id]


def test_fired_ids_are_pruned_to_reminders_still_in_the_file(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-29 07:00 one\n- [ ] 2026-10-29 07:30 two\n"))
    hb = engine(tmp_path, reminders)
    hb.tick(sig(AM, idle_s=900))
    assert len(hb.rules[0].state["fired"]) == 2
    reminders.items = reminders.items[1:]
    hb.tick(sig(AM + timedelta(minutes=1), idle_s=900))
    assert hb.rules[0].state["fired"] == [reminders.items[0].id]


def test_rate_limit_caps_spoken_nudges(tmp_path):
    hb = engine(tmp_path, min_gap_between_nudges_min=20, max_nudges_per_hour=2, focus_break={"after_min": 10})
    times = [t for t, n in run(hb, PM, 60, idle_s=10, app="Xcode")]
    assert 1 <= len(times) <= 2
    assert all(b - a >= timedelta(minutes=20) for a, b in zip(times, times[1:]))


def test_bubble_only_nudges_skip_the_rate_limit(tmp_path):
    hb = engine(tmp_path, max_nudges_per_hour=0, welcome_back={"away_min": 1})
    assert hb.tick(sig(AM)) == []  # morning is spoken, so the zero cap drops it
    nudges = hb.tick(sig(AM + timedelta(minutes=5)))
    assert [n.rule for n in nudges] == ["welcome_back"]


def test_a_failing_rule_does_not_stop_reminders(tmp_path):
    reminders = ListReminders(*parse("- [ ] 2026-10-29 13:00 Stretch\n"))
    hb = engine(tmp_path, reminders)

    def boom(signals, reminders):
        raise RuntimeError("bug")

    hb.rules[1].check = boom
    assert [n.rule for n in hb.tick(sig(PM))] == ["reminders"]
