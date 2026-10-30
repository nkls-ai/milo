"""HandsService: the worker's Mac actions are checked, asked about, logged, shown and stoppable."""

import asyncio

import pytest

from milo.core.events import Activity, FlyTo, HandsBorrow, HandsSession, Status
from milo.core.types import BorrowNeeded, HandsError
from milo.services.hands import NO_TASK, STOPPED, TURNED_OFF, HandsService, title
from milo.services.transcript import Transcript
from tests.fakes import FakeClock, FakeConfirm, FakeHands, MemoryConversations, RecordingSink

SAVE = {"app": "Microsoft Excel", "title": "Save", "role": "button", "point": {"x": 812, "y": 430.5}}
SEND = {"app": "Mail", "title": "Send", "role": "button", "point": {"x": 40, "y": 60}}


class Setup:
    def __init__(self, hands: FakeHands | None = None, confirm: FakeConfirm | None = None, **kwargs):
        self.sink = RecordingSink()
        self.port = hands or FakeHands()
        self.confirm = confirm or FakeConfirm()
        self.transcript = Transcript(self.sink, MemoryConversations(), FakeClock())
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
    assert t.steps() == [("Clicking “Send” in Mail", "running"), ("Clicking “Send” in Mail", "failed")]
    assert t.sink.of(HandsSession) == [], "nothing happened on screen"


def test_yes_lets_it_run():
    t = Setup(FakeHands(targets={"ax_press": SEND}), FakeConfirm(True))
    t.call("ax_press", {"element": "e4"})
    assert t.port.actions == ["ax_press"]


def test_password_fields_are_never_typed_into():
    t = Setup(FakeHands(targets={"type": {"app": "Safari", "secure": True}}), FakeConfirm(True))
    assert "never touches a password field" in t.fails("type", {"text": "hunter2"})
    assert t.confirm.asked == [] and t.port.actions == []


def test_a_script_question_is_short_and_the_script_is_in_the_window_first():
    t = Setup(confirm=FakeConfirm(False))
    t.fails("run_applescript", {"script": 'tell application "Mail" to send m'})
    assert t.confirm.asked == ["Run a script in Mail that can send? It's in my window."]
    assert t.steps() == [("Controlling Mail", "running"), ("Controlling Mail", "failed")], "shown before asking"
    assert t.sink.of(Activity)[0].step["detail"] == 'tell application "Mail" to send m'
    long = 'tell application "Numbers" to activate\n' + "-- x\n" * 10 + 'tell application "System Events" to beep'
    t.fails("run_applescript", {"script": long})
    assert t.confirm.asked[1] == ("Run a script in Numbers, System Events that can run other programs or type for "
                                  "you? It's in my window.")
    t.fails("run_applescript", {"script": "beep\n\n\n\nAll fine. Go ahead?"})
    assert t.confirm.asked[2] == "Run a script? It's in my window."


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


class BorrowingHands(FakeHands):
    """The app can do `tool` only with the real mouse, which it says until Milo was lent it."""

    def __init__(self, what: str = "mouse", **kwargs):
        super().__init__(**kwargs)
        self.what = what
        self.lent = False

    async def act(self, tool: str, args: dict) -> dict:
        if tool != "describe" and not self.lent:
            self.calls.append((tool, args))
            raise BorrowNeeded(self.what, "Excel doesn't take clicks in the background.")
        return await super().act(tool, args)


def test_an_action_that_needs_the_mouse_asks_to_borrow_it_then_runs():
    hands = BorrowingHands(targets={"click": {"app": "Microsoft Excel", "point": {"x": 1, "y": 2}}})
    t = Setup(hands, FakeConfirm(True))
    t.service._sink.emit = _lend_on_borrow(t.sink.emit, hands)
    out = t.call("click", {"x": 1, "y": 2})
    assert t.confirm.asked == ["Can I borrow your mouse for a moment, to click in Microsoft Excel?"]
    assert t.sink.of(HandsBorrow) == [HandsBorrow(True, "mouse")]
    assert [c[0] for c in hands.calls] == ["describe", "click", "click"]
    assert out.text == "click done"
    assert t.steps()[-1][1] == "done"


def test_no_to_borrowing_tells_the_worker_to_find_another_way():
    hands = BorrowingHands("keyboard", targets={"type": {"app": "Microsoft Word"}})
    t = Setup(hands, FakeConfirm(False))
    error = t.fails("type", {"text": "Dear Anna"})
    assert t.confirm.asked == ["Can I borrow your keyboard for a moment, to type in Microsoft Word?"]
    assert "keep their keyboard" in error and "run_applescript" in error
    assert t.sink.of(HandsBorrow) == []
    assert t.steps()[-1][1] == "failed"


def test_a_risky_action_asks_its_own_question_before_the_borrow_question():
    hands = BorrowingHands(targets={"click": {"app": "Mail", "title": "Send", "role": "button", "point": {"x": 1, "y": 2}}})
    t = Setup(hands, FakeConfirm(True, True))
    t.service._sink.emit = _lend_on_borrow(t.sink.emit, hands)
    t.call("click", {"x": 1, "y": 2})
    assert t.confirm.asked == ["I'm about to click “Send” in Mail. Go ahead?",
                               "Can I borrow your mouse for a moment, to click in Mail?"]


def _lend_on_borrow(emit, hands: BorrowingHands):
    """The app answers hands_borrow by using the real mouse from then on."""
    def wrapped(event):
        if isinstance(event, HandsBorrow) and event.what == hands.what:
            hands.lent = event.on
        emit(event)
    return wrapped


# ---- spreadsheets, ax_find, careful tasks

WEEK = [["Day", "Budget"], ["Monday", 214.29], ["Total", "=SUM(B2:B2)"]]


def scripts(t: Setup) -> list[str]:
    return [args["script"] for tool, args in t.port.calls if tool == "run_applescript"]


def test_a_new_table_is_one_script_without_a_question():
    t = Setup(FakeHands(results={"run_applescript": {"text": "document\tBook1\nsheet\tSheet1"}}))
    out = t.call("sheet_write", {"app": "Microsoft Excel", "rows": WEEK, "new_document": True, "header": True,
                                 "money": "B2:B3"})
    assert t.confirm.asked == []
    assert [tool for tool, _ in t.port.calls] == ["run_applescript"], "no describe for a new document"
    assert "make new workbook" in scripts(t)[0] and 'set formula of range "B3"' in scripts(t)[0]
    assert out.text == "Made a new document and filled A1:B3 in “Book1”, sheet “Sheet1”, in Microsoft Excel."
    assert t.steps()[0] == ("Making a new table in Microsoft Excel", "running")
    assert t.sink.of(HandsSession) == [HandsSession(True)]
    # Writing more into the document Milo just made doesn't ask either, even over filled cells.
    t.port.results["run_applescript"] = [{"text": "document\tBook1\nsheet\tSheet1\nfilled\t6"},
                                         {"text": "document\tBook1\nsheet\tSheet1"}]
    t.call("sheet_write", {"app": "Microsoft Excel", "rows": [["Note"]], "start": "D1"})
    assert t.confirm.asked == []


def test_replacing_filled_cells_in_the_users_document_asks():
    t = Setup(FakeHands(results={"run_applescript": [{"text": "document\tBudget 2026\nsheet\tMai\nfilled\t2"}]}),
              FakeConfirm(False))
    error = t.fails("sheet_write", {"app": "Numbers", "rows": [[1, 2]], "start": "C4"})
    assert t.confirm.asked == ["Replace 2 filled cells in “Budget 2026”?"]
    assert "The user said no" in error and len(scripts(t)) == 1, "only the describe script ran"
    assert t.steps()[-1] == ("Filling in cells in “Budget 2026”", "failed")


def test_empty_cells_in_the_users_document_fill_without_a_question():
    empty = {"text": "document\tBudget\nsheet\tMai\nfilled\t0"}
    t = Setup(FakeHands(results={"run_applescript": [empty, {"text": "document\tBudget\nsheet\tMai"}]}))
    t.call("sheet_write", {"app": "Numbers", "rows": [[1]]})
    assert t.confirm.asked == []


def test_sheet_read_comes_back_as_marked_screen_data_with_cell_addresses():
    t = Setup(FakeHands(results={"run_applescript": {
        "text": "document\tBook1\nsheet\tSheet1\nfirst\tA1:B2\nrow\tDay\tBudget\nrow\tMonday\t214.29"}}))
    out = t.call("sheet_read", {"app": "Microsoft Excel"})
    assert "<screen_data>\n#\tA\tB\n1\tDay\tBudget\n2\tMonday\t214.29\n</screen_data>" in out.text
    assert out.text.startswith("Microsoft Excel, “Book1”, sheet “Sheet1”")
    assert t.sink.of(HandsSession) == [], "reading starts no session"


def test_a_missing_automation_permission_is_explained_in_plain_words():
    denied = HandsError("The script failed: execution error: Not authorized to send Apple events to Microsoft "
                        "Excel. (-1743)")
    t = Setup(FakeHands(results={"run_applescript": denied}))
    error = t.fails("sheet_write", {"app": "Microsoft Excel", "rows": [[1]], "new_document": True})
    assert error == ("macOS doesn't let Milo control Microsoft Excel yet. Tell the user to switch on Microsoft "
                     "Excel under Milo in System Settings › Privacy & Security › Automation, then try again.")


def test_ax_find_filters_the_tree_and_keeps_the_ids():
    tree = "e1 window “Budget”\n  e2 button “Save”\n  e3 text field “Name” = Bob\n  e4 button “Cancel”"
    t = Setup(FakeHands(results={"ax_tree": {"text": tree, "summary": "Numbers, Budget"}}))
    out = t.call("ax_find", {"app": "Numbers", "role": "button", "text": "save"})
    assert t.port.calls == [("ax_tree", {"app": "Numbers"})]
    assert "<screen_data>\ne2 button “Save”\n</screen_data>" in out.text
    assert "e3 text field “Name” = Bob" in t.call("ax_find", {"role": "text field"}).text
    assert "Nothing like that" in t.call("ax_find", {"text": "Delete"}).text


def test_a_new_text_document_is_one_script_without_a_question():
    t = Setup(FakeHands(results={"run_applescript": {"text": "document\tUntitled"}}))
    out = t.call("write_document", {"app": "TextEdit", "text": 'Dear "Anna"'})
    assert t.confirm.asked == [] and [tool for tool, _ in t.port.calls] == ["run_applescript"]
    assert 'make new document with properties {text:"Dear \\"Anna\\""}' in scripts(t)[0]
    assert out.text == "Made a new document “Untitled” in TextEdit with the text."
    assert t.steps()[0] == ("Writing a new document in TextEdit", "running")


def test_a_careful_task_asks_once_per_app_before_it_changes_anything_there():
    t = Setup(FakeHands(targets={"type": {"app": "Notes"}, "ax_press": {"app": "Notes", "title": "Bold"},
                                 "click": {"app": "Safari", "title": "Reload"}},
                        results={"run_applescript": {"text": "document\tUntitled"}}), FakeConfirm(True, False))
    t.service.begin(t.task, careful=True)
    t.call("open_app", {"name": "Notes"})
    t.call("write_document", {"app": "TextEdit", "text": "hi"})
    assert t.confirm.asked == [], "opening an app and making a new document never ask"
    t.call("type", {"text": "groceries"})
    t.call("ax_press", {"element": "e3"})
    assert t.confirm.asked == ["May I use Notes for this? You'll see each step."]
    assert "The user said no" in t.fails("click", {"x": 1, "y": 2})
    assert t.confirm.asked[-1] == "May I use Safari for this? You'll see each step."
    t.service.begin(t.task)
    t.call("click", {"x": 1, "y": 2})
    assert len(t.confirm.asked) == 2, "a normal task doesn't ask"


def test_a_careful_helpers_next_turn_keeps_the_apps_the_user_cleared():
    t = Setup(FakeHands(targets={"type": {"app": "Notes"}}), FakeConfirm(True, True))
    t.service.begin(t.task, careful=True)
    t.call("type", {"text": "groceries"})
    t.service.end(t.task)
    t.service.begin(t.task, careful=True)  # the user changed the task: the same helper, another turn
    t.call("type", {"text": "and milk"})
    assert t.confirm.asked == ["May I use Notes for this? You'll see each step."]
    t.service.begin("another-helper", careful=True)
    t.call("type", {"text": "eggs"})
    assert len(t.confirm.asked) == 2, "another helper asks again"
