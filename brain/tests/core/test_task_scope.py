"""Which of Milo's tools and instructions a helper gets, from the task's own words."""

from milo.core.task_scope import ALL, KINDS, TOOLS_ENV, ToolScope, scope_for, server_env, trim_instructions
from milo.core.types import ToolServer


def test_a_calendar_task_in_german_gets_the_calendar_and_nothing_else():
    scope = scope_for("Lies die Termine im Kalender des Nutzers für morgen und fasse sie kurz zusammen.", screen=False)
    assert scope.kinds == frozenset({"calendar"})
    assert scope.simple, "a known kind off the screen: a light model may do it"


def test_kinds_are_found_in_english_and_german():
    cases = {
        "Find the latest email from Anna and say what it says.": {"mail"},
        "Schreib Anna eine Mail als Entwurf": {"mail"},
        "Put milk on my shopping list": {"notes", "reminders"},
        "Add a reminder to call the dentist": {"reminders"},
        "Find my electricity bills in Documents": {"files"},
        "Such die Stromrechnung im Ordner Downloads": {"files"},
        "What's the weather tomorrow?": {"shortcuts"},
        "Send me the PDF on my phone": {"files", "phone"},
        "When is my sister's birthday?": {"memory"},
        "Search the web for flights to Lisbon": set(),
    }
    for text, kinds in cases.items():
        assert scope_for(text, screen=False).kinds == frozenset(kinds), text


def test_a_task_whose_kind_is_unclear_gets_every_tool():
    scope = scope_for("Sort this out for me, you know what I mean", screen=False)
    assert scope.kinds is None and not scope.simple
    assert server_env(scope) == ()


def test_a_screen_task_gets_only_the_connections_it_names():
    assert scope_for("Make the header row of the open Excel sheet blue", screen=True).kinds == frozenset()
    both = scope_for("Put tomorrow's calendar into a new Excel table", screen=True)
    assert both.kinds == frozenset({"calendar"}) and not both.simple, "screen work is never the light model's"


def test_the_connection_server_is_told_which_tools_to_serve():
    milo = ToolServer("milo", ("python", "-m", "milo.connect"), (("MILO_HOME", "/h"),))
    other = ToolServer("milo-mac", ("python", "-m", "milo.mcp_server"))
    scope = ToolScope(frozenset({"mail", "calendar"}), screen=False)
    assert server_env(scope) == ((TOOLS_ENV, "calendar,mail"),)
    scoped = scope.servers((milo, other))
    assert scoped[0].env == (("MILO_HOME", "/h"), (TOOLS_ENV, "calendar,mail")) and scoped[1] == other
    assert ALL.servers((milo, other)) == (milo, other)


AGENTS = """\
# You are Milo

Intro.

## How to answer

- Short.

## The user's apps

Calendar and mail.

## Using the Mac

Excel and clicks.

## Undo

Undo points.

## Memory

memory_search.

## Reminders

milo_remind.

## Routines

Recipes.

## My own notes

The user's own section.

## Limits

work/ only.
"""


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("#")]


def test_a_calendar_read_gets_the_instructions_for_apps_but_not_the_screen_or_routines():
    trimmed = trim_instructions(AGENTS, ToolScope(frozenset({"calendar"}), screen=False))
    assert headings(trimmed) == ["# You are Milo", "## How to answer", "## The user's apps", "## Undo",
                                 "## My own notes", "## Limits"], "a section Milo doesn't know stays"


def test_a_screen_task_gets_using_the_mac_and_undo():
    trimmed = trim_instructions(AGENTS, ToolScope(frozenset(), screen=True))
    assert headings(trimmed) == ["# You are Milo", "## How to answer", "## Using the Mac", "## Undo",
                                 "## My own notes", "## Limits"]


def test_every_tool_means_every_section():
    assert trim_instructions(AGENTS, ToolScope(None, screen=True)) == AGENTS
    assert "## Using the Mac" not in trim_instructions(AGENTS, ALL), "ALL is every connection, off the screen"
    assert trim_instructions(AGENTS, ToolScope(frozenset({"memory", "reminders"}), screen=False)).count("## ") == 7


def test_kinds_name_only_known_connections():
    assert set(KINDS) == {"calendar", "reminders", "mail", "notes", "shortcuts", "files", "phone", "memory"}
