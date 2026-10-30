"""Contract test: the shared fixture decodes into our types and round-trips back to the same JSON."""

import json
from pathlib import Path

import pytest

from milo.core import events as ev
from milo.core.types import Emotion, ListenMode, MiloState
from tests import fakes
from milo.core import ports

FIXTURE = json.loads((Path(__file__).parents[3] / "protocol" / "messages.json").read_text())

OUTBOUND = {
    "state": lambda m: ev.StateChanged(MiloState(m["state"])),
    "emotion": lambda m: ev.EmotionChanged(Emotion(m["emotion"])),
    "bubble": lambda m: ev.Bubble(m["text"]),
    "heard": lambda m: ev.Heard(m["text"]),
    "level": lambda m: ev.Level(m["value"]),
    "dictation": lambda m: ev.Dictation(m["text"]),
    "status": lambda m: ev.Status(m["text"]),
    "ui_config": lambda m: ev.UiConfig(m["dictate_key"], m["talk_key"], m["hands_free_max_s"], m["whats_this_key"],
                                       m["character"]),
    "partial": lambda m: ev.Partial(m["text"]),
    "history": lambda m: ev.History(m["entries"]),
    "entry": lambda m: ev.EntryChanged(m["entry"]),
    "reply_delta": lambda m: ev.ReplyDelta(m["id"], m["text"]),
    "activity": lambda m: ev.Activity(m["task_id"], m["step"]),
    "look_request": lambda m: ev.LookRequest(m["id"], m["mode"]),
    "looking": lambda m: ev.Looking(m["on"]),
    "hands_request": lambda m: ev.HandsRequest(m["id"], m["tool"], m["args"]),
    "hands_session": lambda m: ev.HandsSession(m["on"]),
    "fly_to": lambda m: ev.FlyTo(m["point"]),
    "confirm": lambda m: ev.Confirm(m["id"], m["question"]),
    "confirm_done": lambda m: ev.ConfirmDone(m["id"], m["answer"]),
    "app_request": lambda m: ev.AppRequest(m["id"], m["op"], m["args"]),
    "helpers": lambda m: ev.Helpers(m["helpers"]),
    "hands_borrow": lambda m: ev.HandsBorrow(m["on"], m["what"]),
    "remote": lambda m: ev.Remote(m["channel"], m["label"], m["state"], m["paused"], m["detail"]),
}


@pytest.mark.parametrize("msg", FIXTURE["brain_to_app"], ids=lambda m: m["type"])
def test_every_outbound_event_round_trips(msg):
    assert OUTBOUND[msg["type"]](msg).to_wire() == msg


def test_fixture_covers_every_event_type():
    defined = {cls.type for cls in ev.Event.__subclasses__()}
    assert defined == {m["type"] for m in FIXTURE["brain_to_app"]}
    assert {s.value for s in MiloState} == {m["state"] for m in FIXTURE["brain_to_app"] if m["type"] == "state"}


@pytest.mark.parametrize("msg", FIXTURE["app_to_brain"], ids=lambda m: m["type"])
def test_every_inbound_command_parses(msg):
    cmd = ev.parse_command(msg)
    assert cmd.type == msg["type"]


def test_fixture_covers_every_command_type():
    defined = {cls.type for cls in ev.Command.__subclasses__()}
    assert defined == {m["type"] for m in FIXTURE["app_to_brain"]}


def test_screen_commands_parse_into_their_values():
    look, error = (ev.parse_command(m) for m in FIXTURE["app_to_brain"] if m["type"] == "look_result")
    assert look.capture.app == "Microsoft Excel" and look.capture.image.endswith(".png") and not look.capture.error
    assert not error.capture.image and "Screen Recording" in error.capture.error
    assert ev.parse_command({"type": "hands_result", "id": "h", "ok": False, "error": "nope"}) == \
        ev.HandsResult("h", False, {}, "nope")
    assert ev.parse_command({"type": "hands_stop"}) == ev.HandsStop("user")


def test_parsed_values():
    assert ev.parse_command({"type": "listen_start", "mode": "dictate"}) == ev.ListenStart(ListenMode.DICTATE)
    assert ev.parse_command({"type": "context", "app": "", "idle_s": -3}) == ev.ContextUpdate(None, 0.0)
    assert ev.parse_command({"type": "confirm_answer", "id": "q1", "yes": False}) == ev.ConfirmAnswer("q1", False)
    assert ev.parse_command({"type": "app_response", "id": "a1", "ok": True, "result": [1]}) == \
        ev.AppResponse("a1", True, [1])
    assert ev.parse_command({"type": "app_response", "id": "a1", "ok": "yes"}).ok is False
    assert ev.parse_command({"type": "remote_pause", "on": True}) == ev.RemotePause(True)
    assert ev.parse_command({"type": "remote_forget"}) == ev.RemoteForget()
    with pytest.raises(ev.ProtocolError):
        ev.parse_command({"type": "remote_pause", "on": "yes"})
    assert ev.parse_command({"type": "stop_helper", "id": "c0ffee12ab34"}) == ev.StopHelper("c0ffee12ab34")
    with pytest.raises(ev.ProtocolError):
        ev.parse_command({"type": "stop_helper", "id": " "})


@pytest.mark.parametrize("raw", [
    [], {"type": "nope"}, {"type": "listen_start", "mode": "shout"}, {"type": "text", "text": "  "},
    {"type": "text"}, {"type": "mute"}, {"type": "context", "idle_s": "soon"},
    {"type": "whats_this"}, {"type": "whats_this", "capture": "screen"}, {"type": "hands_result", "id": "h"},
    {"type": "hands_result", "id": "h", "ok": True, "result": []},
    {"type": "confirm_answer", "id": "q1", "yes": "no"}, {"type": "confirm_answer", "yes": True},
    {"type": "app_response", "ok": True},
])
def test_bad_commands_raise_protocol_error(raw):
    with pytest.raises(ev.ProtocolError):
        ev.parse_command(raw)


@pytest.mark.parametrize("fake, port", [
    (fakes.FakeClock(), ports.Clock), (fakes.FakeHarness(), ports.Harness),
    (fakes.FakeTranscriber(), ports.Transcriber), (fakes.FakeVoice(), ports.Voice),
    (fakes.FakeAudioInput(), ports.AudioInput), (fakes.FakeAudioOutput(), ports.AudioOutput),
    (fakes.UpperCleaner(), ports.TextCleaner), (fakes.RecordingSink(), ports.EventSink),
    (fakes.ListReminders(), ports.ReminderSource), (fakes.MemoryLedger(), ports.UsageLedger),
    (fakes.MemoryHistory(), ports.DictationHistory), (fakes.CountingBudget(), ports.LlmBudget),
    (fakes.ScriptedEngine(), ports.ProactiveEngine),
    (fakes.FakeLiveModel(), ports.LiveModel), (fakes.MemoryProfile(), ports.ProfileMemory),
    (fakes.ListReminders(), ports.ReminderBook), (fakes.FakeConfirm(), ports.Confirmer),
])
def test_fakes_satisfy_their_ports(fake, port):
    assert isinstance(fake, port)
