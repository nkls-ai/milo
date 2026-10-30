"""Brain routes wire commands to services. Wired with fakes through tests/services/stack.py."""

import asyncio
import json
from pathlib import Path

import pytest

from milo.brain import Brain
from milo.config import UiSettings
from milo.core.events import (Bubble, Dictation, EmotionChanged, Heard, Level, ListenStart, ListenStop, Mute,
                              StateChanged, TextInput, UiConfig, parse_command)
from milo.core.types import Emotion, ListenMode, MiloState, Nudge
from tests.fakes import FakeLiveModel, FakeTranscriber
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
                                UiConfig("right_command", "right_control")]
    s.ui.set_state(MiloState.THINKING)
    s.ui.set_emotion(Emotion.SAD)
    assert brain.greeting()[:2] == [StateChanged(MiloState.THINKING), EmotionChanged(Emotion.SAD)]


def check_listen_start(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert s.mic.active and s.mic.starts == 1
    expected = MiloState.DICTATING if msg["mode"] == "dictate" else MiloState.LISTENING
    assert s.ui.state is expected


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
    assert s.sink.events == []  # the stack has no transcript, so there is nothing to send


def check_context(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert s.context.app == msg["app"]
    assert s.context.idle_s() == msg["idle_s"]


def check_mute(s: Stack, msg: dict) -> None:
    run(s, parse_command(msg))
    assert s.heartbeat.muted is msg["on"]


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
        [waiting] = s.bridge._waiting
        s.bridge._waiting[msg["id"]] = s.bridge._waiting.pop(waiting)
        await s.brain.handle(parse_command(msg))
        try:
            return await calling
        except Exception as e:
            return str(e)

    assert asyncio.run(go()) == (msg["result"] if msg["ok"] else msg["error"])


CHECKS = {
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


@pytest.mark.parametrize("msg", FIXTURE["app_to_brain"], ids=lambda m: f"{m['type']}-{m.get('mode', '')}")
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
