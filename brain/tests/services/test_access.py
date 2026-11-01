"""The first time Milo controls an app (ADR 0025).

The user: "Make sure that everything is very smooth, so how the user will be asked if it's allowed to use Excel
and so on." The system's own question ("Milo wants access to control Microsoft Excel") used to pop up in the
middle of a task, and a refusal came back to the worker as a confusing error. Now Milo says in one line what is
about to happen, then the system asks; a no ends that part cleanly with a Fix it button; and an app that is
already allowed shows nothing at all.
"""

import asyncio
from pathlib import Path

from milo.core.access import Access, AccessAnswer
from milo.core.events import AccessNote, Confirm
from milo.core.types import AppRef, HandsError, StepStatus
from milo.services.access import AccessGate
from milo.services.tool_requests import ToolRequests
from tests.fakes import FakeAccess, FakeHands, RecordingSink
from tests.services.stack import Stack
from tests.services.test_permits import ExcelApp, Worker

FILL = ("sheet_write", {"app": "Microsoft Excel", "rows": [["Rent", 900]], "start": "A2"})
BOLD = ("run_applescript", {"script": 'tell application "Microsoft Excel" to set bold of font object of '
                                      'range "A1:B1" of active sheet to true'})
CLICK = ("click", {"x": 300, "y": 200})
SHOT = ("screenshot", {})


def stack(*turns, hands: FakeHands | None = None, **access) -> tuple[Stack, Worker, FakeAccess]:
    worker = Worker(*turns)
    sink = RecordingSink()
    fake = FakeAccess(sink=sink, **access)
    s = Stack(harness=worker, background=FakeHands(), hands_port=hands or ExcelApp(), sink=sink, access=fake)
    worker.hands = s.hands
    return s, worker, fake


def run(s: Stack, *tasks: str) -> None:
    async def go():
        for task in tasks:
            s.tasks.submit(task, title=task, screen=True, user_asked=True)
            await s.tasks.idle()
    asyncio.run(go())


def notes(s: Stack) -> list[tuple[str, str, str]]:
    return [(n.need, n.state, n.text) for n in s.sink.of(AccessNote)]


# ---- the story


def test_before_the_system_asks_milo_says_what_is_coming_then_the_work_goes_on():
    s, worker, access = stack([FILL, BOLD], apps={"Microsoft Excel": "ask"})
    run(s, "put the numbers into Excel")

    assert access.asked() == ["Microsoft Excel"], "the system asked once, for Excel"
    [said] = [text for need, state, text in notes(s) if state == "ask"]
    assert said == "macOS will ask once whether I may use Microsoft Excel. Click Allow."
    [before] = access.shown
    assert any(isinstance(e, AccessNote) and e.state == "ask" for e in before), "the line came first"
    assert worker.errors == []
    assert s.hands_port.actions.count("run_applescript") >= 2, "the fill and the script both ran"
    assert s.sink.of(Confirm) == [], "auto mode: no question of Milo's own on top"


def test_an_app_that_is_already_allowed_shows_nothing_ever():
    s, worker, access = stack([FILL, BOLD, CLICK], [FILL])
    run(s, "fill it in", "and again")
    assert notes(s) == []
    assert access.asked() == []
    assert worker.errors == []


def test_the_system_is_asked_once_even_when_two_steps_need_the_app():
    s, worker, access = stack([BOLD, FILL, BOLD], apps={"Microsoft Excel": "ask"})
    run(s, "format it")
    assert access.asked() == ["Microsoft Excel"]
    assert len([n for n in s.sink.of(AccessNote) if n.state == "ask"]) == 1


def test_dont_allow_ends_that_part_cleanly_with_a_fix_it_button():
    s, worker, access = stack([FILL, BOLD], apps={"Microsoft Excel": "ask"}, clicks={"Microsoft Excel": "no"})
    run(s, "fill it in")

    assert notes(s)[-1] == ("control", "no", "Okay, I won't use Microsoft Excel. If you change your mind, Fix it "
                                             "shows the switch.")
    [note] = [n for n in s.sink.of(AccessNote) if n.state == "no"]
    assert (note.app, note.bundle) == ("Microsoft Excel", "com.microsoft.Excel"), "Fix it opens Milo › Excel"
    assert "run_applescript" not in s.hands_port.actions, "nothing reached Excel"
    assert len(worker.errors) == 2
    assert all("didn't allow Milo to control Microsoft Excel" in e for e in worker.errors)
    assert "another way" in worker.errors[0], "the worker may still finish the job another way"
    assert access.asked() == ["Microsoft Excel"], "asked once; the second try doesn't ask again"


def test_an_app_the_user_turned_down_before_isnt_asked_about_again():
    s, worker, access = stack([FILL], apps={"Microsoft Excel": "no"})
    run(s, "fill it in")
    assert access.asked() == []
    assert notes(s) == [("control", "no", "I'm not allowed to use Microsoft Excel yet. Fix it shows the switch.")]
    assert worker.errors and "didn't allow" in worker.errors[0]


def test_each_task_hears_about_a_refusal_once_in_the_bubble():
    s, worker, access = stack([FILL, FILL], [FILL], apps={"Microsoft Excel": "no"})
    run(s, "first", "second")
    assert [state for _, state, _ in notes(s)] == ["no", "no"], "once per task, not once per step"


def test_an_app_that_cant_tell_goes_ahead_as_before():
    # An older app answers nothing; an app that isn't installed can't be asked about.
    s, worker, access = stack([FILL], apps={"Microsoft Excel": "unknown"})
    run(s, "fill it in")
    assert notes(s) == [] and access.asked() == [] and worker.errors == []
    assert "run_applescript" in s.hands_port.actions


class Steps:
    def __init__(self):
        self.steps = []

    def task_step(self, task_id, step):
        self.steps.append((task_id, step.title, step.status))


def test_the_step_shows_in_the_task_while_the_system_asks():
    steps = Steps()
    gate = AccessGate(FakeAccess(apps={"Microsoft Excel": "ask"}), RecordingSink(), transcript=steps, pause_s=0)
    asyncio.run(gate.control(AppRef("Microsoft Excel"), "t1"))
    assert steps.steps == [("t1", "Asking to use Microsoft Excel", StepStatus.RUNNING),
                           ("t1", "Asking to use Microsoft Excel", StepStatus.DONE)]


# ---- clicks and screenshots


def test_a_click_without_the_switch_for_windows_stops_before_anything_happens():
    s, worker, access = stack([CLICK, CLICK], ui="no")
    run(s, "click the cell")
    assert notes(s) == [("ui", "no", "To work in other apps' windows I need Accessibility. Fix it shows where to "
                                     "switch it on.")]
    assert s.hands_port.calls == [], "not even a describe"
    assert len(worker.errors) == 2 and "sheet_write" in worker.errors[0], "it points the worker at the scripts"


def test_a_screenshot_without_screen_access_says_so_first():
    s, worker, access = stack([SHOT], screen="no")
    run(s, "look at it")
    assert notes(s) == [("screen", "no", "To see the screen I need Screen Recording. Fix it shows where to switch "
                                         "it on.")]
    assert "window_text" in worker.errors[0]


def test_scripts_dont_need_the_switch_for_windows():
    s, worker, access = stack([FILL, BOLD], ui="no", screen="no")
    run(s, "fill it in")
    assert notes(s) == [] and worker.errors == []


# ---- a refusal macOS reports only after the fact


def test_a_refusal_found_while_running_still_shows_the_fix_it_button():
    denied = HandsError("The script failed: Not authorized to send Apple events to Microsoft Excel. (-1743)")
    s, worker, access = stack([BOLD], hands=FakeHands(results={"run_applescript": denied}))
    run(s, "format it")
    assert [(need, state) for need, state, _ in notes(s)] == [("control", "no")]
    assert "didn't allow Milo to control Microsoft Excel" in worker.errors[0]


# ---- Mail and Notes through the connection tools


def test_the_connection_tools_ask_the_brain_before_their_first_script():
    sink = RecordingSink()
    access = FakeAccess(apps={"Mail": "ask"}, clicks={"Mail": "no"}, sink=sink)
    gate = AccessGate(access, sink, pause_s=0)
    requests = ToolRequests(approvals=None, bridge=None, access=gate)
    answer = asyncio.run(requests.handle({"op": "access", "app": "Mail"}))
    assert answer["ok"] is True and answer["result"]["allowed"] is False
    assert "didn't allow Milo to control Mail" in answer["result"]["error"]
    assert [n.state for n in sink.of(AccessNote)] == ["ask", "no"]

    access.apps["Notes"] = Access.YES
    assert asyncio.run(requests.handle({"op": "access", "app": "Notes"}))["result"] == {"allowed": True}


def test_without_a_gate_the_tool_socket_lets_the_connection_go_ahead():
    requests = ToolRequests(approvals=None, bridge=None)
    assert asyncio.run(requests.handle({"op": "access", "app": "Mail"}))["result"] == {"allowed": True}


# ---- where sandboxed apps may save


def test_where_a_sandboxed_app_may_save_comes_from_the_app():
    container = "/Users/you/Library/Containers/com.microsoft.Excel/Data"
    gate = AccessGate(FakeAccess(places={"Microsoft Excel": [container]}), RecordingSink(), pause_s=0)
    assert asyncio.run(gate.places(AppRef("Microsoft Excel"))) == (container,)
    assert asyncio.run(gate.places(AppRef("TextEdit"))) is None, "None: anywhere"


# ---- the brain stays portable


def test_the_brains_access_logic_names_no_macos_switch_page_or_error_code():
    root = Path(__file__).parents[2] / "src" / "milo"
    for path in (root / "core" / "access.py", root / "services" / "access.py"):
        text = path.read_text(encoding="utf-8")
        for word in ("System Settings", "Privacy", "x-apple", "-1743", "AppleScript", "osascript", "Accessibility",
                     "Screen Recording"):
            assert word not in text, f"{path.name} names {word!r}; that belongs to the app"


def test_the_wire_answer_reads_anything_it_doesnt_know_as_unknown():
    assert AccessAnswer.from_wire({"access": "maybe"}).access is Access.UNKNOWN
    assert AccessAnswer.from_wire(None).access is Access.UNKNOWN
    got = AccessAnswer.from_wire({"access": "yes", "bundle": "com.microsoft.Excel"}, AppRef("Microsoft Excel"))
    assert got.app == AppRef("Microsoft Excel", "com.microsoft.Excel")


# ---- the wire to the app


def test_the_bridge_asks_the_app_and_an_app_that_doesnt_know_the_op_means_unknown():
    from milo.core.access import Need
    from milo.core.events import AppRequest, AppResponse
    from milo.services.app_bridge import AppAccessLink, AppBridge

    sink = RecordingSink()
    bridge = AppBridge(sink, timeout_s=1)
    link = AppAccessLink(bridge)

    async def go():
        check = asyncio.create_task(link.check(Need.CONTROL, AppRef("Microsoft Excel")))
        await asyncio.sleep(0)
        [sent] = sink.of(AppRequest)
        assert (sent.op, sent.args) == ("access.check", {"need": "control", "app": "Microsoft Excel", "bundle": "",
                                                         "launch": True})
        bridge.resolve(AppResponse(sent.id, True, {"access": "ask", "bundle": "com.microsoft.Excel",
                                                   "system": "macOS", "button": "Allow"}))
        answer = await check
        assert answer == AccessAnswer(Access.ASK, AppRef("Microsoft Excel", "com.microsoft.Excel"), "macOS", "",
                                      "Allow")

        old = asyncio.create_task(link.request(Need.UI))
        await asyncio.sleep(0)
        bridge.resolve(AppResponse(sink.of(AppRequest)[-1].id, False, error="unknown op access.request"))
        assert (await old).access is Access.UNKNOWN

        places = asyncio.create_task(link.places(AppRef("Microsoft Excel")))
        await asyncio.sleep(0)
        bridge.resolve(AppResponse(sink.of(AppRequest)[-1].id, True, {"sandboxed": True, "places": ["/c"]}))
        assert await places == ("/c",)

    asyncio.run(go())


# ---- Milo's own yes comes first


def test_a_script_the_user_turns_down_never_starts_the_app_or_brings_up_the_systems_question():
    s, worker, access = stack([BOLD], apps={"Microsoft Excel": "ask"})
    s.permits.ask = "step"

    async def go():
        async def say_no():
            seen = 0
            while True:
                await asyncio.sleep(0)
                for c in s.sink.of(Confirm)[seen:]:
                    s.approvals.answer(c.id, False)
                seen = len(s.sink.of(Confirm))
        bot = asyncio.create_task(say_no())
        s.tasks.submit("format it", title="format it", screen=True, user_asked=True)
        await s.tasks.idle()
        bot.cancel()
    asyncio.run(go())
    assert s.sink.of(Confirm), "Milo asked his own question"
    assert access.calls == [], "no check, no start, no system question"
    assert notes(s) == []


def test_a_script_milo_never_runs_doesnt_touch_the_system_either():
    password = ("run_applescript", {"script": 'tell application "Keychain Access" to get password of item 1'})
    s, worker, access = stack([password], apps={"Keychain Access": "ask"})
    run(s, "get it")
    assert access.calls == []


def test_the_tool_socket_checks_only_the_apps_the_connection_tools_script():
    gate = AccessGate(FakeAccess(apps={"Microsoft Excel": "ask"}), RecordingSink(), pause_s=0)
    requests = ToolRequests(approvals=None, bridge=None, access=gate)
    answer = asyncio.run(requests.handle({"op": "access", "app": "Microsoft Excel"}))
    assert answer["ok"] is False and "only for the apps" in answer["error"]
