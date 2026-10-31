"""A task the user asked for by voice never feels like silence: one short line at about 8 s, then quiet until the
result or a question (ADR 0032). The app gets the step the helper is on, for the caption under the outline."""

import asyncio

from milo.core.types import Step, StepStatus
from milo.services.helpers import Helper
from milo.services.updates import UpdateMode, Updates, progress_line
from tests.fakes import ScriptedHarness, WorkerScript
from tests.services.stack import Stack, settle

R = StepStatus.RUNNING


def app_step(title: str, kind: str = "app") -> Step:
    return Step("s1", kind, title, "", R)


def helper(*steps: Step, language: str = "") -> Helper:
    h = Helper("t1", 1, "Budget", "make a budget", True, 0.0, language=language)
    for s in steps:
        h.record(s)
    return h


def installed(name: str) -> bool:
    return name == "Microsoft Excel"


def test_the_line_says_what_the_helper_does_in_the_users_language():
    excel = app_step("Opening Microsoft Excel")
    assert progress_line(helper(excel), installed) == "Opening Microsoft Excel now…"
    assert progress_line(helper(excel, language="de"), installed) == "Ich öffne gerade Microsoft Excel…"
    assert progress_line(helper(app_step("Looking in your calendar")), installed) == "Checking your calendar…"
    assert progress_line(helper(app_step("Looking through your mail for “Anna”"), language="de"),
                         installed) == "Ich gehe deine Mails durch…"
    assert progress_line(helper(language="fr"), installed) == "J'y suis encore…"
    assert progress_line(helper(app_step("Opening Evil.app"), language="xx"), installed) == "Still on it…", \
        "no name Milo can't vouch for is spoken"


def test_an_app_step_wins_over_bookkeeping_after_it():
    h = helper(app_step("Opening Microsoft Excel"), Step("s2", "edit", "Noting how things were, to undo with", "", R))
    assert progress_line(h, installed) == "Opening Microsoft Excel now…"


def stack(*actions, updates: str = "bubble", via: str = "voice") -> Stack:
    s = Stack(harness=ScriptedHarness(WorkerScript(*actions)))
    s.tasks.updates = Updates(s.ui, lambda: UpdateMode(updates), s.clock)
    s.tasks._progress_after_s = 0.05
    s.tasks._transcript.user("make a budget", via)
    return s


def run(s: Stack, wait: float = 0.3) -> None:
    async def go():
        s.tasks.submit("make a budget in Excel", title="Budget")
        await asyncio.sleep(wait)
        await s.tasks.idle()
        await settle()

    asyncio.run(go())


def test_a_voice_task_still_working_after_a_while_says_one_line_then_the_result():
    s = stack(app_step("Opening Microsoft Excel"), ("sleep", 0.2), "Your budget is ready.")
    run(s)
    assert s.voice.spoken[-1] == "Your budget is ready."
    assert len(s.voice.spoken) == 2 and s.voice.spoken[0].endswith("…"), "one line, nothing more"


def test_no_line_for_a_quick_task_a_typed_one_or_quiet_mode():
    for s in (stack("Done."), stack(("sleep", 0.2), "Done.", via="typed"),
              stack(("sleep", 0.2), "Done.", updates="quiet")):
        run(s)
        assert s.voice.spoken == ["Done."]


def test_the_app_sees_the_screen_helpers_current_mac_step():
    s = Stack(harness=ScriptedHarness(WorkerScript(("sleep", 0.05), "ok"), name="screen"),
              background=ScriptedHarness(name="background"))

    async def go():
        h = s.tasks.submit("fill in the budget", title="Budget", screen=True)
        await settle()
        s.tasks.screen_step(h.id, Step("hands_1", "app", "Filling in cells in “Budget”", "", R))
        assert s.tasks.snapshot().helpers[0] == {"id": h.id, "title": "Budget", "status": "working",
                                                  "step": "Filling in cells in “Budget”", "screen": True}
        await s.tasks.idle()

    asyncio.run(go())


def test_the_mac_tools_steps_reach_the_screen_helper_through_the_transcript():
    from milo.services.orchestrator import ScreenSteps

    class Seen:
        steps: list = []

        def task_step(self, id, step):
            self.steps.append(id)

        def screen_step(self, id, step):
            self.steps.append(("helper", id))

    seen = Seen()
    ScreenSteps(seen, lambda: seen).task_step("t1", Step("hands_1", "app", "Opening Numbers", "", R))
    assert seen.steps == ["t1", ("helper", "t1")]
