"""The first prompt a helper gets: its task, the user's language, and for a screen helper its tools by name."""

from milo.core.hands import TOOLS
from milo.services.helpers import Helper
from milo.services.task_runner import first_prompt


def helper(**kw) -> Helper:
    return Helper("t1", 1, "YouTube in Chrome", "Open Chrome on youtube.com.", True, 0.0, **kw)


def test_a_screen_helper_is_told_its_tools_so_it_doesnt_list_them_first():
    # 2026-10-31: a Codex helper's first step listed every tool, ~11,600 tokens that each later step sent again.
    prompt = first_prompt(helper(), no_screen=False, tools=True)
    assert "on the milo-mac server: " + ", ".join(t.name for t in TOOLS) in prompt
    assert "use open_app or open_url, never keys" in prompt
    assert "milo-mac" not in first_prompt(helper(), no_screen=False, tools=False)


def test_a_helper_answers_in_the_language_the_user_asked_in():
    assert "(The user speaks German: write `say` in German.)" in first_prompt(helper(language="de"), no_screen=False)
    assert "The user speaks" not in first_prompt(helper(), no_screen=False)
