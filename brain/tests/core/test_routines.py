"""The routine file format, schedules in plain words, and finding a routine by what the user called it."""

from datetime import datetime, time

import pytest

from milo.core.routines import (RecipeError, Routine, RoutineInput, Schedule, find, input_name, parse, parse_schedule,
                                render, slugify)

RECIPE = """\
---
name: Monday report
description: Sums last week's sales files into a one-page report.
inputs:
  - name: month
    ask: Which month?
    default: last month
  - name: folder
    ask: "Which folder: Sales or Shop?"
schedule: every Monday at 09:00
apps: [Numbers, "Pages, the app"]
paused: no
last_run: 2026-10-27 09:00, done
version: 2
owner: me
---

## Goal

A one-page report.

## Steps

1. Open the sales folder for {month}.
   Check: there is one file per day.
"""


def test_a_recipe_reads_with_every_field():
    r = parse(RECIPE, "monday-report")
    assert r.name == "Monday report" and r.slug == "monday-report"
    assert r.inputs == (RoutineInput("month", "Which month?", "last month"),
                        RoutineInput("folder", "Which folder: Sales or Shop?", ""))
    assert r.schedule == "every Monday at 09:00"
    assert r.apps == ("Numbers", "Pages, the app")
    assert not r.paused and r.version == 2 and r.last_run == "2026-10-27 09:00, done"
    assert r.body.startswith("## Goal") and "Check: there is one file per day." in r.body
    assert r.extra == (("owner", "me"),)


def test_render_and_parse_round_trip():
    r = parse(RECIPE, "monday-report")
    assert parse(render(r), "monday-report") == r
    assert render(parse(render(r), "monday-report")) == render(r)
    assert "owner: me" in render(r)


def test_values_that_need_quotes_get_them():
    r = Routine("x", "Report", description="- starts with a dash", inputs=(RoutineInput("q", "[odd]", '"quoted"'),),
                body="Do it.")
    assert parse(render(r), "x") == r


def test_a_bare_recipe_has_defaults():
    r = parse("---\nname: Tidy downloads\n---\nMove old files.", "tidy-downloads")
    assert r == Routine("tidy-downloads", "Tidy downloads", body="Move old files.")


def test_yes_no_is_not_a_boolean_trap():
    r = parse("---\nname: Norway\ndescription: no\npaused: yes\n---\n", "norway")
    assert r.description == "no" and r.paused


@pytest.mark.parametrize("text, words", [
    ("name: x\n---\n", "three dashes"),
    ("---\nname: x\n", "never ends"),
    ("---\ndescription: y\n---\n", "name"),
    ("---\nname: x\nthis is not a key\n---\n", "line 3"),
    ("---\nname: x\nname: y\n---\n", "twice"),
    ("---\nname: x\nversion: two\n---\n", "whole number"),
    ("---\nname: x\npaused: maybe\n---\n", "yes or no"),
    ("---\nname: x\ninputs:\n  - ask: Which?\n---\n", "short name"),
    ("---\nname: x\ninputs:\n  - name: m\n  - name: m\n---\n", "twice"),
    ("---\nname: x\ninputs:\n  - name: m\n    colour: red\n---\n", "colour"),
    ("---\nname: \"x\n---\n", "quote"),
])
def test_broken_recipes_say_what_to_fix(text, words):
    with pytest.raises(RecipeError, match=words):
        parse(text, "x")


def test_fingerprint_follows_the_recipe_not_the_bookkeeping():
    r = parse(RECIPE, "monday-report")
    from dataclasses import replace
    assert replace(r, name="Weekly report", schedule="", last_run="today", paused=True, version=3).fingerprint() \
        == r.fingerprint()
    assert replace(r, body=r.body + "\n2. Mail it to Anna.").fingerprint() != r.fingerprint()
    assert replace(r, inputs=()).fingerprint() != r.fingerprint()


def test_slugs_and_input_names():
    assert slugify("Monday report") == "monday-report"
    assert slugify("Mütter's Größe!") == "mutter-s-groe"
    assert slugify("!!!") == "routine"
    assert slugify("x" * 80) == "x" * 48
    assert input_name("The Month") == "the_month" and input_name("") == "" and input_name("9lives") == ""


def test_find_by_what_the_user_said():
    routines = [Routine("monday-report", "Monday report"), Routine("tidy-downloads", "Tidy downloads"),
                Routine("monday-mail", "Monday mail")]
    assert find(routines, "monday-report").name == "Monday report"
    assert find(routines, "the Monday Report").name == "Monday report"
    assert find(routines, "monday report routine").name == "Monday report"
    assert find(routines, "downloads").name == "Tidy downloads"
    assert find(routines, "monday") is None  # two of them
    assert find(routines, "taxes") is None and find(routines, "") is None


@pytest.mark.parametrize("text, expected", [
    ("every Monday at 9", "every Monday at 09:00"),
    ("Mondays and Thursdays at 8:30am", "every Monday and Thursday at 08:30"),
    ("every mon, wed and fri at 18:00", "every Monday, Wednesday and Friday at 18:00"),
    ("every weekday at 8", "every weekday at 08:00"),
    ("weekends at 10", "every weekend day at 10:00"),
    ("daily at 6pm", "every day at 18:00"),
    ("every day at 12am", "every day at 00:00"),
    ("every day at noon", "every day at 12:00"),
    ("on the 1st of every month at 9", "on the 1st of every month at 09:00"),
    ("monthly on the 22nd at 9.30", "on the 22nd of every month at 09:30"),
    ("every Monday at 09:00", "every Monday at 09:00"),
])
def test_schedules_in_plain_words(text, expected):
    schedule = parse_schedule(text)
    assert str(schedule) == expected
    assert parse_schedule(str(schedule)) == schedule


@pytest.mark.parametrize("text", ["", "every Monday", "at 9", "every blue moon at 9", "every day at 25:00",
                                  "every month at 9", "on the 40th of every month at 9"])
def test_schedules_that_dont_parse(text):
    with pytest.raises(RecipeError):
        parse_schedule(text)


def test_last_and_next_due():
    monday_9 = Schedule(time(9), frozenset({0}))
    friday = datetime(2026, 10, 30, 12, 0)  # a Friday
    assert monday_9.last_due(friday) == datetime(2026, 10, 26, 9, 0)
    assert monday_9.next_due(friday) == datetime(2026, 11, 2, 9, 0)
    assert monday_9.last_due(datetime(2026, 10, 26, 9, 0)) == datetime(2026, 10, 26, 9, 0)
    assert monday_9.next_due(datetime(2026, 10, 26, 9, 0)) == datetime(2026, 11, 2, 9, 0)
    first = Schedule(time(9), monthday=31)
    assert first.last_due(friday) == datetime(2026, 8, 31, 9, 0)  # September has no 31st
    assert first.next_due(friday) == datetime(2026, 10, 31, 9, 0)
