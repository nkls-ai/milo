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
    "ui_config": lambda m: ev.UiConfig(m["dictate_key"], m["talk_key"], m["hands_free_max_s"]),
    "partial": lambda m: ev.Partial(m["text"]),
    "history": lambda m: ev.History(m["entries"]),
    "entry": lambda m: ev.EntryChanged(m["entry"]),
    "reply_delta": lambda m: ev.ReplyDelta(m["id"], m["text"]),
    "activity": lambda m: ev.Activity(m["task_id"], m["step"]),
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


def test_parsed_values():
    assert ev.parse_command({"type": "listen_start", "mode": "dictate"}) == ev.ListenStart(ListenMode.DICTATE)
    assert ev.parse_command({"type": "context", "app": "", "idle_s": -3}) == ev.ContextUpdate(None, 0.0)


@pytest.mark.parametrize("raw", [
    [], {"type": "nope"}, {"type": "listen_start", "mode": "shout"}, {"type": "text", "text": "  "},
    {"type": "text"}, {"type": "mute"}, {"type": "context", "idle_s": "soon"},
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
    (fakes.ListReminders(), ports.ReminderBook),
])
def test_fakes_satisfy_their_ports(fake, port):
    assert isinstance(fake, port)
