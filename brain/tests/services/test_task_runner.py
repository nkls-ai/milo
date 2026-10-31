"""The first prompt a helper gets: its task, the user's language, and for a screen helper its tools by name."""

from milo.core.hands import TOOLS
from milo.core.task_scope import ToolScope
from milo.services.helpers import Helper
from milo.services.task_runner import NEEDS_TOOLS, first_prompt


def helper(**kw) -> Helper:
    return Helper("t1", 1, "YouTube in Chrome", "Open Chrome on youtube.com.", True, 0.0, **kw)


def test_a_screen_helper_is_told_its_tools_so_it_doesnt_list_them_first():
    # 2026-10-31: a Codex helper's first step listed every tool, ~11,600 tokens that each later step sent again.
    prompt = first_prompt(helper(), no_screen=False, tools=True)
    for tool in TOOLS:
        assert f"- mcp__milo_mac__{tool.name}(" in prompt
    assert "Never open things with keys" in prompt
    assert "milo-mac" not in first_prompt(helper(), no_screen=False, tools=False)


def test_every_helper_is_told_its_connection_tools_with_their_arguments():
    calendar = Helper("t2", 2, "Termine", "Lies die Termine für morgen.", False, 0.0,
                      scope=ToolScope(frozenset({"calendar"})))
    prompt = first_prompt(calendar, no_screen=True)
    assert "- mcp__milo__calendar_events(start?, end?, query?)" in prompt and "mail_search" not in prompt
    assert NEEDS_TOOLS in prompt, "a helper short of a tool can ask for all of them"
    unscoped = first_prompt(Helper("t3", 3, "Sort", "Sort it out.", False, 0.0), no_screen=True)
    assert "mcp__milo__mail_search(" in unscoped and NEEDS_TOOLS not in unscoped


def test_switched_off_connections_are_not_named():
    prompt = first_prompt(Helper("t4", 4, "Sort", "Sort it out.", False, 0.0), no_screen=True,
                          available=frozenset({"calendar"}))
    assert "calendar_events" in prompt and "mail_search" not in prompt


def test_a_helper_answers_in_the_language_the_user_asked_in():
    assert "(The user speaks German: write `say` in German.)" in first_prompt(helper(language="de"), no_screen=False)
    assert "The user speaks" not in first_prompt(helper(), no_screen=False)
