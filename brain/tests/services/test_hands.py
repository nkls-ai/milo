"""HandsService: the worker's Mac actions are checked, asked about, logged, shown and stoppable."""

import asyncio

import pytest

from milo.core.events import Activity, FlyTo, HandsSession, Status
from milo.core.types import HandsError
from milo.services.hands import NO_TASK, STOPPED, TURNED_OFF, HandsService, title
from milo.services.transcript import Transcript
from tests.fakes import FakeClock, FakeConfirm, FakeHands, MemoryTranscript, RecordingSink

SAVE = {"app": "Microsoft Excel", "title": "Save", "role": "button", "point": {"x": 812, "y": 430.5}}
SEND = {"app": "Mail", "title": "Send", "role": "button", "point": {"x": 40, "y": 60}}


class Setup:
    def __init__(self, hands: FakeHands | None = None, confirm: FakeConfirm | None = None, **kwargs):
        self.sink = RecordingSink()
        self.port = hands or FakeHands()
        self.confirm = confirm or FakeConfirm()
        self.transcript = Transcript(self.sink, MemoryTranscript(), FakeClock())
        self.task = self.transcript.task_started("tidy the budget")
        self.service = HandsService(self.port, self.confirm, self.sink, transcript=self.transcript, **kwargs)
        self.service.begin(self.task)

    def call(self, tool: str, args: dict):
        return asyncio.run(self.service.call(tool, args))

    def fails(self, tool: str, args: dict) -> str:
        with pytest.raises(HandsError) as e:
            self.call(tool, args)
        return str(e.value)

    def steps(self) -> list[tuple[str, str]]:
        return [(a.step["title"], a.step["status"]) for a in self.sink.of(Activity)]


def test_a_click_is_described_logged_shown_and_run():
    t = Setup(FakeHands(targets={"click": SAVE}))
    out = t.call("click", {"x": 640, "y": 412})
    assert t.port.calls == [("describe", {"tool": "click", "x": 640, "y": 412}), ("click", {"x": 640, "y": 412})]
    clicking = "Clicking “Save” in Microsoft Excel"
    assert t.steps() == [(clicking, "running"), (clicking, "done")]
    assert t.sink.of(HandsSession) == [HandsSession(True)]
    assert t.sink.of(FlyTo) == [FlyTo({"x": 812.0, "y": 430.5})]
    assert out.text == "click done" and out.image == ""
    assert t.service.active


def test_reading_tools_need_no_describe_and_start_no_session():
    t = Setup(FakeHands(results={"window_text": {"text": "Rent 900", "summary": "Microsoft Excel, Budget.xlsx"}}))
    out = t.call("window_text", {"app": "Microsoft Excel"})
    assert t.port.calls == [("window_text", {"app": "Microsoft Excel"})]
    assert t.sink.of(HandsSession) == [] and t.sink.of(FlyTo) == []
    assert out.text.startswith("Microsoft Excel, Budget.xlsx\n[Everything between <screen_data>")
    assert "<screen_data>\nRent 900\n</screen_data>" in out.text
    assert t.steps()[0] == ("Reading the Microsoft Excel window", "running")


def test_a_screenshot_comes_back_as_an_image_with_its_size():
    t = Setup(FakeHands(results={"screenshot": {"image": "/x/shot.png", "width": 1400, "height": 875}}))
    out = t.call("screenshot", {})
    assert out.image == "/x/shot.png" and "1400x875 pixels" in out.text


def test_a_risky_click_waits_for_yes_and_no_means_it_never_runs():
    t = Setup(FakeHands(targets={"ax_press": SEND}), FakeConfirm(False))
    error = t.fails("ax_press", {"element": "e4"})
    assert t.confirm.asked == ["I'm about to click “Send” in Mail. Go ahead?"]
    assert "The user said no" in error
    assert t.port.actions == []
    assert t.steps() == [("Clicking “Send” in Mail", "failed")]
    assert t.sink.of(HandsSession) == [], "nothing happened on screen"


def test_yes_lets_it_run():
    t = Setup(FakeHands(targets={"ax_press": SEND}), FakeConfirm(True))
    t.call("ax_press", {"element": "e4"})
    assert t.port.actions == ["ax_press"]


def test_password_fields_are_never_typed_into():
    t = Setup(FakeHands(targets={"type": {"app": "Safari", "secure": True}}), FakeConfirm(True))
    assert "never touches a password field" in t.fails("type", {"text": "hunter2"})
    assert t.confirm.asked == [] and t.port.actions == []


def test_a_risky_script_names_the_app_in_its_question():
    t = Setup(confirm=FakeConfirm(False))
    t.fails("run_applescript", {"script": 'tell application "Mail" to send m'})
    assert t.confirm.asked == ["I'm about to run a script in Mail that can send. The script is in my window. "
                              "Go ahead?"]


def test_applescript_can_be_turned_off():
    assert Setup(applescript=False).fails("run_applescript", {"script": "beep"}) == TURNED_OFF


@pytest.mark.parametrize("tool, args, message", [
    ("draw", {}, "There is no tool called 'draw'."),
    ("click", {"x": 1}, "click needs y."),
    ("click", {"x": "1", "y": 2}, "click: x must be a number."),
    ("click", {"x": True, "y": 2}, "click: x must be a number."),
    ("click", {"x": 1, "y": 2, "button": "middle"}, "click: button must be one of left, right."),
    ("type", {"text": "a", "speed": 3}, "type has no argument speed."),
])
def test_bad_arguments_are_explained(tool, args, message):
    t = Setup()
    assert t.fails(tool, args) == message
    assert t.port.calls == []


def test_without_a_running_task_nothing_runs():
    t = Setup()
    t.service.end(t.task)
    assert t.fails("list_apps", {}) == NO_TASK


def test_the_user_taking_over_stops_the_running_action_and_every_later_one():
    gate = asyncio.Event()
    t = Setup(FakeHands(targets={"click": SAVE}, gate=gate))

    async def run():
        clicking = asyncio.create_task(t.service.call("click", {"x": 1, "y": 2}))
        for _ in range(10):
            await asyncio.sleep(0)
        assert t.service.active
        t.service.stop("escape")
        with pytest.raises(HandsError) as e:
            await clicking
        assert str(e.value) == STOPPED
        with pytest.raises(HandsError) as later:
            await t.service.call("list_apps", {})
        assert str(later.value) == STOPPED

    asyncio.run(run())
    assert t.port.cancels == 1
    assert t.sink.of(HandsSession) == [HandsSession(True), HandsSession(False)]
    assert t.sink.of(FlyTo)[-1] == FlyTo(None)
    assert t.sink.of(Status) == [Status("Okay, I stopped. It's all yours.")]
    assert t.steps()[-1] == ("Clicking “Save” in Microsoft Excel", "failed")


def test_the_next_task_starts_unstopped():
    t = Setup()
    t.service.stop("user")
    t.service.begin("next-task")
    assert t.call("list_apps", {}).text == "list_apps done"


def test_the_end_of_a_task_takes_the_frame_away_and_brings_milo_home():
    t = Setup(FakeHands(targets={"click": SAVE}))
    t.call("click", {"x": 1, "y": 2})
    t.service.end(t.task)
    assert t.sink.events[-2:] == [FlyTo(None), HandsSession(False)]
    assert not t.service.active


@pytest.mark.parametrize("tool, args, target, expected", [
    ("open_app", {"name": "Numbers"}, {}, "Opening Numbers"),
    ("ax_set_value", {"element": "e2", "text": "x"}, {"app": "Safari", "title": "Email"},
     "Filling in “Email” in Safari"),
    ("type", {"text": "Dear Anna, thanks for the photos"}, {"app": "Mail"},
     "Typing “Dear Anna, thanks for the pho…” in Mail"),
    ("key", {"combo": "cmd+s"}, {"app": "Pages"}, "Pressing ⌘S in Pages"),
    ("key", {"combo": "tab"}, {}, "Pressing Tab"),
    ("click", {"x": 1, "y": 2, "double": True}, {"app": "Finder"}, "Double-clicking in Finder"),
    ("click", {"x": 1, "y": 2}, {}, "Clicking on the screen"),
    ("scroll", {"dy": 3}, {"app": "Safari"}, "Scrolling in Safari"),
    ("run_applescript", {"script": 'tell application "Numbers" to activate'}, {}, "Controlling Numbers"),
    ("list_apps", {}, {}, "Checking which apps are open"),
])
def test_steps_read_like_plain_sentences(tool, args, target, expected):
    assert title(tool, args, target) == expected
