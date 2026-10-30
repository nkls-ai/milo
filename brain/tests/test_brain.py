"""Brain routes wire commands to services. Wired with fakes through tests/services/stack.py."""

import asyncio
import json
from pathlib import Path

import pytest

from milo.brain import Brain
from milo.config import UiSettings
from milo.core.events import (Bubble, Dictation, EmotionChanged, HandsSession, Heard, Level, ListenStart, ListenStop,
                              Looking, Mute, StateChanged, Status, TextInput, UiConfig, parse_command)
from milo.core.events import Routines
from milo.core.routines import Routine
from milo.core.types import Emotion, HandsError, ListenMode, MiloState, Nudge, ScreenCapture
from milo.services.app_bridge import AppEyes, AppHands
from tests.fakes import FakeEyes, FakeHands, FakeLiveModel, FakeTranscriber
from milo.services.helpers import HelperStatus
from tests.fakes import ScriptedHarness, WorkerScript
from tests.services.stack import Stack, settle

FIXTURE = json.loads((Path(__file__).parents[2] / "protocol" / "messages.json").read_text())

STRETCH = Nudge("focus_break", Emotion.HAPPY, "Time to stretch.", speak=True)
REMINDER = Nudge("reminders", Emotion.EXCITED, "Call the dentist.", speak=True)


def run(s: Stack, *commands, brain: Brain | None = None) -> None:
    async def go():
        for command in commands:
            await (brain or s.brain).handle(command)
            await settle()

    asyncio.run(go())


def flow(s: Stack) -> list:
    return [e for e in s.sink.events if not isinstance(e, Level)]


def test_greeting_draws_the_current_state_and_sends_the_configured_keys():
    s = Stack()
    brain = Brain(s.ui, s.listening, s.live_talk, s.context, s.heartbeat,
                  UiSettings("right_command", "right_control"))
    assert brain.greeting() == [StateChanged(MiloState.IDLE), EmotionChanged(Emotion.NEUTRAL),
                                UiConfig("right_command", "right_control", whats_this_key="ctrl+option+m")]
    s.ui.set_state(MiloState.THINKING)
    s.ui.set_emotion(Emotion.SAD)
    assert brain.greeting()[:2] == [StateChanged(MiloState.THINKING), EmotionChanged(Emotion.SAD)]


def check_listen_start(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert s.mic.active and s.mic.starts == 1
    expected = MiloState.DICTATING if msg["mode"] == "dictate" else MiloState.LISTENING
    assert s.ui.state is (MiloState.IDLE if msg.get("tentative") else expected)


def check_listen_stop(s: Stack, msg: dict) -> None:
    run(s, ListenStart(ListenMode.TALK), parse_command(msg))
    assert not s.mic.active and len(s.transcriber.calls) == 1


def check_listen_cancel(s: Stack, msg: dict) -> None:
    run(s, ListenStart(ListenMode.TALK), parse_command(msg))
    assert not s.mic.active and s.transcriber.calls == []
    assert s.ui.state is MiloState.IDLE


def check_text(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert len(s.model.turns) == 1 and s.model.turns[0].endswith("\n" + msg["text"])


def check_listen_confirm(s: Stack, msg: dict) -> None:
    run(s, ListenStart(ListenMode.DICTATE), parse_command(msg))
    assert s.mic.active and s.ui.state is MiloState.DICTATING


def check_get_history(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    # The stack has no transcript, so only the routines go out: the window lists them.
    assert s.sink.events == [Routines([], [])]


def check_context(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert s.context.app == msg["app"]
    assert s.context.idle_s() == msg["idle_s"]


def check_mute(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert s.heartbeat.muted is msg["on"]


def answered(s: Stack, msg: dict, ask) -> object:
    """Start a request through the bridge, feed the fixture message to the brain, return what the request got."""
    async def go():
        waiting = asyncio.create_task(ask())
        await settle()
        await s.brain.handle(parse_command(msg))
        return await waiting

    return asyncio.run(go())


def check_look_result(s: Stack, msg: dict) -> None:
    if msg["id"] != "look-1":  # nobody waits for it: dropped quietly
        run(s, parse_command(msg))
        return
    capture = answered(s, msg, lambda: AppEyes(s.bridge).look())
    assert capture.app == "Microsoft Excel" and capture.text.startswith("Rent")
    assert capture.image == "", "a path outside state/screens is never read"


def check_whats_this(s: Stack, msg: dict) -> None:
    s.model.script.append(["[concerned] That looks like a scam."])
    run(s, parse_command(msg))
    assert s.sink.of(Heard) == [Heard("What's this?")]
    assert "Your parcel is waiting" in s.model.turns[0] and "<screen_data>" in s.model.turns[0]


def check_hands_result(s: Stack, msg: dict) -> None:
    async def act():
        try:
            return await AppHands(s.bridge).act("click", {"x": 1, "y": 2})
        except HandsError as e:
            return e

    if msg["id"] == "hands-2":
        next(s.bridge._ids)  # ids count up across kinds: make this the bridge's second request
        assert answered(s, msg, act) == {"text": "Clicked."}
    else:
        run(s, parse_command(msg))


def check_hands_stop(s: Stack, msg: dict) -> None:
    s.hands.begin("t1")
    s.hands._start_session({})
    run(s, parse_command(msg))
    assert s.sink.events[-2:] == [HandsSession(False), Status("Okay, I stopped. It's all yours.")]
    assert s.hands_port.cancels == 1


def check_confirm_answer(s: Stack, msg: dict) -> None:
    async def go():
        asking = asyncio.create_task(s.approvals.confirm("Send it?"))
        await settle()
        s.approvals._pending = (msg["id"], *s.approvals._pending[1:])  # the fixture's id
        await s.brain.handle(parse_command(msg))
        return await asking

    assert asyncio.run(go()) is msg["yes"]


def check_app_response(s: Stack, msg: dict) -> None:
    async def go():
        calling = asyncio.create_task(s.bridge.call("calendar.events", {}))
        await settle()
        [waiting] = s.bridge._pending
        s.bridge._pending[msg["id"]] = s.bridge._pending.pop(waiting)
        await s.brain.handle(parse_command(msg))
        try:
            return await calling
        except Exception as e:
            return str(e)

    assert asyncio.run(go()) == (msg["result"] if msg["ok"] else msg["error"])


def check_stop_helper(s: Stack, msg: dict) -> None:
    gate = asyncio.Event()
    s.harness = ScriptedHarness(WorkerScript(gate, "never"))
    s.runner._harness = s.harness

    async def go():
        helper = s.tasks.submit("count to a million")
        await settle()
        s.tasks._supervisors[msg["id"]] = s.tasks._supervisors.pop(helper.id)  # the fixture's id
        helper.id = msg["id"]
        await s.brain.handle(parse_command(msg))
        await s.tasks.idle()
        return helper

    helper = asyncio.run(go())
    assert helper.status is HelperStatus.STOPPED and s.harness.played[0].cancelled


def check_routine(s: Stack, msg: dict) -> None:
    report = Routine("monday-report", "Monday report", body="1. Add up the sales.\n   Check: one total.")
    s.routine_book.save(report)
    s.routine_book.save(Routine("tidy-downloads", "Tidy downloads", paused=True, body="Tidy."))
    s.routine_state.data = {"approved": {"monday-report": report.fingerprint()}}
    s.routines._state = s.routine_state.load()

    async def go():
        await s.brain.handle(parse_command(msg))
        await s.routines.idle()
        await s.tasks.idle()

    asyncio.run(go())
    if msg["action"] == "run":
        assert [h.title for h in s.tasks.helpers] == ["Monday report"]
        assert "Add up the sales." in s.harness.calls[0][0]
    else:
        assert not s.routine_book.get("tidy-downloads").paused


def check_routine_draft_answer(s: Stack, msg: dict) -> None:
    s.routine_state.data = {"drafts": {msg["id"]: {"name": "Invoice folder", "base": "invoice-folder",
                                                   "schedule": None, "ready": True}}}
    s.routines._state = s.routine_state.load()
    s.routine_book.drafts[msg["id"]] = "---\nname: Invoice folder\n---\n\n1. Move the invoices.\n"

    async def go():
        await s.brain.handle(parse_command(msg))
        await s.routines.idle()

    asyncio.run(go())
    saved = s.routine_book.get("invoice-folder")
    assert (saved is not None) is msg["save"] and not s.routine_book.drafts
    assert s.routine_state.data["approved"]["invoice-folder"] == saved.fingerprint()


CHECKS = {
    "routine": check_routine,
    "routine_draft_answer": check_routine_draft_answer,
    "stop_helper": check_stop_helper,
    "look_result": check_look_result,
    "whats_this": check_whats_this,
    "hands_result": check_hands_result,
    "hands_stop": check_hands_stop,
    "confirm_answer": check_confirm_answer,
    "app_response": check_app_response,
    "listen_start": check_listen_start,
    "listen_stop": check_listen_stop,
    "listen_cancel": check_listen_cancel,
    "listen_confirm": check_listen_confirm,
    "get_history": check_get_history,
    "text": check_text,
    "context": check_context,
    "mute": check_mute,
}


def test_every_fixture_command_has_a_routing_check():
    assert {m["type"] for m in FIXTURE["app_to_brain"]} == set(CHECKS)


@pytest.mark.parametrize("msg", FIXTURE["app_to_brain"],
                         ids=lambda m: f"{m['type']}-{m.get('mode', '')}{m.get('id', '')}")
def test_every_fixture_command_routes_to_its_service(msg):
    CHECKS[msg["type"]](Stack(transcriber=FakeTranscriber("something")), msg)


def test_mute_without_a_heartbeat_is_harmless():
    s = Stack()
    brain = Brain(s.ui, s.listening, s.live_talk, s.context, None, UiSettings())
    run(s, Mute(True), brain=brain)
    assert s.sink.events == []


def test_a_text_turn_goes_heard_thinking_speaking_bubble_idle():
    s = Stack(model=FakeLiveModel(["[happy] Hello ", "there."]))
    run(s, TextInput("hi Milo"))
    assert flow(s) == [
        Heard("hi Milo"),
        StateChanged(MiloState.THINKING),
        EmotionChanged(Emotion.THINKING),
        EmotionChanged(Emotion.HAPPY),
        StateChanged(MiloState.SPEAKING),
        Bubble("Hello there."),
        StateChanged(MiloState.IDLE),
    ]
    assert s.voice.spoken == ["Hello there."]


def test_dictation_start_stop_emits_cleaned_text():
    s = Stack(transcriber=FakeTranscriber("  ship it  "))
    run(s, parse_command({"type": "context", "app": "Mail", "idle_s": 0}),
        ListenStart(ListenMode.DICTATE), ListenStop())
    assert s.sink.of(Dictation) == [Dictation("SHIP IT")]
    assert s.history.entries == [("SHIP IT", "Mail")]
    assert s.states() == [MiloState.DICTATING, MiloState.TRANSCRIBING, MiloState.IDLE]
    assert s.model.turns == []


def test_mute_stops_nudges_but_reminders_still_show_silently():
    s = Stack()

    async def go():
        await s.brain.handle(Mute(True))
        s.engine.queue.append([STRETCH, REMINDER])
        await s.heartbeat.tick()
        await settle()
        assert s.bubbles() == ["Call the dentist."]
        assert s.voice.spoken == [], "muted: reminders are shown, not spoken"

        await s.brain.handle(Mute(False))
        s.engine.queue.append([STRETCH])
        await s.heartbeat.tick()
        await settle()

    asyncio.run(go())
    assert s.bubbles()[-1] == "Time to stretch."
    assert s.voice.spoken == ["Time to stretch."]
