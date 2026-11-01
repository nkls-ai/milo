"""The view models and the controller, fed recorded event sequences: what QML would see, without QML."""
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QObject

from milo.core.events import parse_command
from milo.desktop import script
from milo.desktop.controller import DesktopController, ViewModels
from milo.desktop.presentation.clock import ManualScheduler

PROTOCOL = Path(__file__).parents[3] / "protocol" / "messages.json"


class Native:
    """A platform that does what it's asked and remembers it."""

    def __init__(self):
        self.pasted, self.calls, self.fixes = [], [], []
        self.paste_result = {"pasted": True}
        self.input_busy = False

    def remember_focus(self): self.calls.append("focus")
    def poll_focus(self): pass
    def take_corrections(self): fixes, self.fixes = self.fixes, []; return fixes
    def set_learning(self, on): self.calls.append(("learn", on))
    def arm_return_to_dictation_target(self): self.calls.append("arm")
    def context(self): return {"app": "Editor", "idle_s": 1.0}
    def capture(self, mode="window"): return {"app": "Editor", "text": "screen"}
    def hands_request(self, tool, args): return {"text": "done"}
    def app_request(self, op, args): return {"pasted": False, "why": "no_field"} if op.startswith("text.") else {}
    def session_event(self, event): self.calls.append(event["type"])
    def meeting_record(self, event, send): self.calls.append("record")
    def paste_dictation(self, text, *, learn=True): self.pasted.append(text); return self.paste_result
    def close(self): pass


class Checked(script.Recorder):
    """Every command the app sends must parse as a real wire command."""

    def send(self, command):
        parse_command(command)
        return super().send(command)


@pytest.fixture
def desktop(tmp_path):
    clock = ManualScheduler()
    views = ViewModels(clock)
    connection, native = Checked(), Native()
    copied = []
    controller = DesktopController(tmp_path, views, connection, native, copy=copied.append)
    controller.on_connection(True)
    connection.commands.clear()
    yield controller, connection, native, clock, copied
    controller.close()


def signals(obj: QObject, *names):
    seen = []
    for name in names:
        getattr(obj, name).connect(lambda *a, n=name: seen.append(n))
    return seen


def test_every_protocol_example_lands_and_every_request_is_answered(desktop):
    controller, connection, *_ = desktop
    fixtures = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    for message in fixtures["brain_to_app"]:
        controller.on_event(message)
    requests = ("look_request", "hands_request", "app_request")
    for request in (e for e in fixtures["brain_to_app"] if e["type"] in requests):
        assert any(c.get("id") == request["id"] for c in connection.commands)


def test_the_level_moves_only_the_meter(desktop):
    controller, *_ = desktop
    presence = controller.views.presence
    names = [n for n in dir(type(presence)) if n.endswith("Changed")]
    seen = signals(presence, *names)
    controller.on_event({"type": "state", "state": "listening"})
    seen.clear()
    for value in (0.1, 0.4, 0.4, 0.2):
        controller.on_event({"type": "level", "value": value})
    assert seen == ["levelChanged"] * 3
    assert presence.level == 0.2


def test_a_turn_through_the_overlay(desktop):
    controller, connection, native, clock, _ = desktop
    presence = controller.views.presence
    celebrated = signals(presence, "celebrate")
    script.play_now(controller, script.welcome())
    presence.ear("armed", "talk")
    assert (presence.phase, presence.mode, presence.shown) == ("armed", "talk", True)
    presence.ear("open", "talk")
    controller.on_event({"type": "state", "state": "listening"})
    controller.on_event({"type": "partial", "text": "what's on"})
    assert presence.phase == "listening" and presence.partial == "what's on" and presence.hint == "Listening"
    presence.ear("caught", "talk")
    assert presence.phase == "caught" and presence.hint == "Got it"
    clock.advance(0.6)
    controller.on_event({"type": "state", "state": "thinking"})
    assert presence.phase == "thinking" and presence.colorMode == "talk"
    controller.on_event({"type": "state", "state": "speaking"})
    controller.on_event({"type": "bubble", "text": "Your standup is at ten."})
    assert presence.speaking and presence.bubble and presence.phase == ""
    controller.on_event({"type": "action_done", "kind": "event", "title": "Dentist"})
    assert celebrated == ["celebrate"]


def test_he_hides_after_the_brains_wait_and_comes_back_for_a_key(desktop):
    controller, _, _, clock, _ = desktop
    presence = controller.views.presence
    controller.on_event({"type": "settings", "settings": [{"section": "ui", "key": "hide_after_s", "value": 5}]})
    clock.advance(6)
    assert not presence.shown
    presence.ear("armed", "dictate")
    assert presence.shown


def test_streaming_updates_one_row_without_a_reset(desktop):
    controller, *_ = desktop
    entries = controller.views.conversations.entries
    script.play_now(controller, script.welcome())
    resets, changed = [], []
    entries.modelReset.connect(lambda: resets.append(1))
    entries.dataChanged.connect(lambda a, b, roles: changed.append((a.row(), b.row())))
    inserted = signals(entries, "rowsInserted")
    controller.on_event({"type": "entry", "entry": {"id": "m9", "ts": "2026-10-30T09:14:00", "kind": "milo",
                                                     "text": "", "done": False, "conversation": script.CONVERSATION}})
    for piece in ("Sure", ", ", "here."):
        controller.on_event({"type": "reply_delta", "id": "m9", "text": piece})
    assert not resets and inserted == ["rowsInserted"]
    last = entries.rowCount() - 1
    assert changed == [(last, last)] * 3
    index = entries.index(last)
    role = {bytes(v).decode(): k for k, v in entries.roleNames().items()}
    assert entries.data(index, role["text"]) == "Sure, here."
    assert entries.data(index, role["streaming"]) is True
    assert controller.views.window.pending == ""


def test_typed_text_goes_to_the_shown_conversation_and_keeps_the_draft_offline(desktop):
    controller, connection, *_ = desktop
    window = controller.views.window
    assert window.sendText("  hello  ", "")
    assert connection.commands[-1] == {"type": "text", "text": "hello", "speak": False}
    window.setSpeakReplies(True)
    assert window.sendText("and the other one?", "c-old")
    assert connection.commands[-1]["conversation"] == "c-old" and connection.commands[-1]["speak"]
    controller.on_connection(False)
    assert not window.sendText("keep this", "")
    assert "reconnecting" in window.notice


def test_opening_searching_and_renaming(desktop):
    controller, connection, *_ = desktop
    conversations, route = controller.views.conversations, controller.views.route
    script.play_now(controller, script.welcome())
    assert [r["section"] for r in conversations.rows][:2] == ["Today", "Today"]
    conversations.open("c-smoke-2")
    assert connection.commands[-1] == {"type": "open_conversation", "id": "c-smoke-2"}
    assert (route.page, route.pageId) == ("conversation", "c-smoke-2")
    assert not conversations.live
    conversations.open(script.CONVERSATION)
    assert route.page == "live" and conversations.live
    conversations.setSearch("photos")
    assert conversations.searching
    conversations._ask()
    assert connection.commands[-1] == {"type": "search_conversations", "query": "photos"}
    controller.on_event({"type": "search_results", "query": "photos", "results": [
        {"conversation": "c-smoke-2", "title": "Train", "kind": "chat", "at": "2026-10-30T09:12:03",
         "snippet": "photos", "via": []}]})
    assert not conversations.searching and conversations.results[0]["id"] == "c-smoke-2"
    conversations.rename("c-smoke-2", " Hamburg trip ")
    assert connection.commands[-1] == {"type": "rename_conversation", "id": "c-smoke-2", "title": "Hamburg trip"}
    conversations.newConversation()
    assert connection.commands[-1] == {"type": "new_conversation"}


def test_answers_need_a_real_choice_and_money_has_no_always(desktop):
    controller, connection, *_ = desktop
    presence, store = controller.views.presence, controller.views.store
    controller.on_event({"type": "confirm", "id": "pay", "question": "Pay?", "money": True, "always": False})
    assert controller.views.window.waiting == 1
    presence.answer("always")
    assert connection.commands == []
    presence.answer("yes")
    assert connection.commands[-1] == {"type": "confirm_answer", "id": "pay", "yes": True, "always": False,
                                       "choice": "yes"}
    assert presence.question == {} and store.confirmations  # gone from the bar, kept until the brain says so
    controller.on_event({"type": "confirm_done", "id": "pay", "answer": "yes"})
    assert store.confirmations == [] and controller.views.window.waiting == 0


def test_dictation_pastes_or_is_kept(desktop):
    controller, _, native, *_ = desktop
    controller.on_event({"type": "dictation", "text": "Sounds good."})
    assert native.pasted == ["Sounds good."] and controller.views.presence.phase == "pasted"
    native.paste_result = {"pasted": False, "why": "secure"}
    opened = signals(controller, "window_requested")
    controller.on_event({"type": "dictation", "text": "secret words"})
    assert controller.views.window.kept["text"] == "secret words"
    assert "protected" in controller.views.window.kept["reason"] and opened


def test_corrections_leave_as_wire_pairs(desktop):
    controller, connection, native, *_ = desktop
    native.fixes = [("Cloud Code", "Claude Code")]
    controller._poll_focus()
    assert connection.commands[-1] == {"type": "dictation_fixed",
                                       "fixes": [{"heard": "Cloud Code", "meant": "Claude Code"}]}


def test_native_failure_replies_and_keeps_the_borrow(desktop):
    controller, connection, native, *_ = desktop

    class NeedsKeyboard(Exception):
        borrow = "keyboard"

    def fail(*_):
        raise NeedsKeyboard("Please lend the keyboard")
    native.hands_request = fail
    controller.on_event({"type": "hands_request", "id": "h1", "tool": "type", "args": {"text": "hi"}})
    answer = connection.commands[-1]
    assert answer["type"] == "hands_result" and not answer["ok"] and answer["result"] == {"borrow": "keyboard"}


def test_office_requests_wait_for_the_actor_and_stop_cancels_it(desktop):
    controller, connection, *_ = desktop

    class Office:
        def __init__(self):
            self.events, self.cancelled, self.callback = [], 0, None
        def request(self, event, callback): self.events.append(event); self.callback = callback
        def cancel(self): self.cancelled += 1
        def close(self): pass
    office = controller.office = Office()
    request = {"type": "hands_request", "id": "office-1", "tool": "sheet_read", "args": {}}
    controller.on_event(request)
    assert office.events == [request] and connection.commands == []
    office.callback({"type": "hands_result", "id": "office-1", "ok": True, "result": {"text": "A1\t42"}})
    assert connection.commands[-1]["result"]["text"] == "A1\t42"
    controller.views.window.stopAll()
    assert office.cancelled == 1


def test_text_milo_kept_gets_copy_under_his_next_line(desktop):
    controller, _, _, _, copied = desktop
    controller.on_event({"type": "app_request", "id": "w1", "op": "text.write", "args": {"text": "Hi Anna"}})
    controller.on_event({"type": "bubble", "text": "It's in my window."})
    presence = controller.views.presence
    assert presence.bubbleAction["kind"] == "copy"
    presence.performBubbleAction()
    assert copied == ["Hi Anna"]


def test_working_frame_follows_the_hands(desktop):
    controller, *_ = desktop
    working = controller.views.working
    script.play_now(controller, script.helpers())
    assert working.active and working.hasPoint and working.step == "Typing “Monday” in Excel"
    assert controller.views.presence.helpersActive
    controller.on_connection(False)
    assert not working.active and not working.hasPoint and not controller.views.presence.helpersActive


def test_ear_signal_from_hotkeys_reaches_the_overlay(tmp_path):
    from PySide6.QtCore import Signal

    class Keys(QObject):
        command = Signal(dict)
        ear = Signal(str, str)
        hands_free = Signal(str)
        focus_requested = Signal()
        status = Signal(str)
        def configure(self, event): pass
        def start(self): pass
        def stop(self): pass
        def set_session(self, on): pass
        def set_meeting(self, on): pass
        def set_synthetic(self, busy): self.busy = busy
    keys = Keys()
    views = ViewModels(ManualScheduler())
    controller = DesktopController(tmp_path, views, Checked(), Native(), keys)
    controller.on_connection(True)
    keys.ear.emit("armed", "dictate")
    assert views.presence.phase == "armed" and views.presence.colorMode == "dictate"
    keys.ear.emit("cancelled", "dictate")
    assert views.presence.phase == ""
    # A double tap locks recording on: the capsule takes the hands-free look, as on the Mac.
    keys.ear.emit("armed", "talk")
    keys.hands_free.emit("talk")
    keys.ear.emit("open", "talk")
    assert views.presence.handsFree
    keys.hands_free.emit("")
    keys.ear.emit("caught", "talk")
    assert not views.presence.handsFree
    controller.close()
