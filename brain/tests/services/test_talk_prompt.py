from milo.services.quick_actions import RULES as QUICK_RULES
from milo.services.talk_prompt import PromptParts, system_prompt


def test_with_quick_actions_on_the_task_rule_leaves_the_calendar_to_them():
    off = system_prompt(PromptParts())
    on = system_prompt(PromptParts(quick=QUICK_RULES))
    everything = "or the user's calendar, reminders, mail, notes, shortcuts or files"
    assert everything in off, "without quick actions a helper does all of it"
    assert everything not in on and "looking something up in the user's mail, notes or files" in on
    assert "come before what the rules above say" not in on, "no rule overrides another"


def test_the_prompt_names_the_platforms_computer():
    assert "the user's Mac: open apps" in system_prompt(PromptParts(computer="Mac"))
    assert "corner of the user's computer." in system_prompt(PromptParts())
    assert "{computer}" not in system_prompt(PromptParts(persona="You are Milo."))
