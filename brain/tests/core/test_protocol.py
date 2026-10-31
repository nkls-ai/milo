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
                                       m["character"], m["meeting_key"]),
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
    "confirm": lambda m: ev.Confirm(m["id"], m["question"], m["always"], m["money"], tuple(m.get("choices", ()))),
    "confirm_done": lambda m: ev.ConfirmDone(m["id"], m["answer"]),
    "app_request": lambda m: ev.AppRequest(m["id"], m["op"], m["args"]),
    "helpers": lambda m: ev.Helpers(m["helpers"]),
    "undo_points": lambda m: ev.UndoPoints(m["points"]),
    "hands_borrow": lambda m: ev.HandsBorrow(m["on"], m["what"]),
    "facts": lambda m: ev.Facts(m["facts"]),
    "routines": lambda m: ev.Routines(m["routines"], m["drafts"]),
    "settings": lambda m: ev.SettingsReport(m["settings"], m["restart"], m["error"]),
    "remote": lambda m: ev.Remote(m["channel"], m["label"], m["state"], m["paused"], m["detail"]),
    "meeting_record": lambda m: ev.MeetingRecord(m["id"], m["dir"], m["on"]),
    "meeting_status": lambda m: ev.MeetingStatus(m["id"], m["phase"], m["title"], m["app"], m["started"], m["elapsed"],
                                                 m["conversation"], tuple(m["speakers"]), m["step"], m["error"],
                                                 m["fix"], m["consent"]),
    "meeting_lines": lambda m: ev.MeetingLines(m["id"], m["lines"], m["reset"]),
    "meeting_notes": lambda m: ev.MeetingNotesReady(m["id"], m["title"], m["started"], m["duration"], m["markdown"],
                                                    m["summary"], tuple(m["decisions"]), tuple(m["todos"]),
                                                    m["followup"], tuple(m["people"]), m["app"], m["conversation"],
                                                    m["folder"], m["reminders"], m["mail"], m["mail_drafted"]),
    "conversations": lambda m: ev.Conversations(m["conversations"], m["current"], m["more"]),
    "conversation": lambda m: ev.ConversationOpened(m["id"], m["info"], m["entries"]),
    "search_results": lambda m: ev.SearchResults(m["query"], m["results"]),
    "reminders": lambda m: ev.RemindersList(m["reminders"]),
    "usage": lambda m: ev.UsageReport(m["span"], m["today"], m["since"], m["daily"], m["sources"], m["apps"],
                                      m["accounts"]),
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
    assert ev.parse_command({"type": "stop_all"}) == ev.StopAll()
    with pytest.raises(ev.ProtocolError):
        ev.parse_command({"type": "stop_helper", "id": " "})
    assert ev.parse_command({"type": "set_setting", "section": "ui", "key": "voice", "value": False}) == \
        ev.SetSetting("ui", "voice", False)


@pytest.mark.parametrize("raw", [
    [], {"type": "nope"}, {"type": "listen_start", "mode": "shout"}, {"type": "text", "text": "  "},
    {"type": "text"}, {"type": "mute"}, {"type": "context", "idle_s": "soon"},
    {"type": "whats_this"}, {"type": "whats_this", "capture": "screen"}, {"type": "hands_result", "id": "h"},
    {"type": "hands_result", "id": "h", "ok": True, "result": []},
    {"type": "confirm_answer", "id": "q1", "yes": "no"}, {"type": "confirm_answer", "yes": True},
    {"type": "app_response", "ok": True},
    {"type": "set_setting", "section": "ui", "key": "character"},
    {"type": "set_setting", "section": "ui", "key": "character", "value": ["pip"]},
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
    (fakes.MemoryUsageHistory(), ports.UsageHistory),
])
def test_fakes_satisfy_their_ports(fake, port):
    assert isinstance(fake, port)


def test_memory_commands_parse_into_their_values():
    assert ev.parse_command({"type": "get_facts"}) == ev.GetFacts()
    assert ev.parse_command({"type": "forget_fact", "id": "f1"}) == ev.ForgetFact("f1")
    assert ev.parse_command({"type": "edit_fact", "id": "f1", "text": "  Anna  is my sister. "}) == \
        ev.EditFact("f1", "Anna is my sister.")
    for bad in ({"type": "forget_fact", "id": " "}, {"type": "edit_fact", "id": "f1", "text": ""},
                {"type": "edit_fact", "id": "f1"}):
        with pytest.raises(ev.ProtocolError):
            ev.parse_command(bad)


def test_routine_commands():
    assert ev.parse_command({"type": "routine", "id": "monday-report", "action": "run"}) == \
        ev.RoutineAction("monday-report", "run")
    assert ev.parse_command({"type": "routine_draft_answer", "id": "d1", "save": False}) == \
        ev.RoutineDraftAnswer("d1", False)
    with pytest.raises(ev.ProtocolError):
        ev.parse_command({"type": "routine", "id": "x", "action": "explode"})
    with pytest.raises(ev.ProtocolError):
        ev.parse_command({"type": "routine_draft_answer", "id": "d1", "save": "yes"})
def test_meeting_commands_parse_into_their_values():
    by_type = {m["type"]: ev.parse_command(m) for m in FIXTURE["app_to_brain"] if m["type"].startswith(("call", "meeting"))}
    assert by_type["call_started"] == ev.CallStarted("Zoom", "us.zoom.xos", "Zoom Meeting")
    assert by_type["call_ended"] == ev.CallEnded("Zoom")
    chunk = by_type["meeting_chunk"]
    assert (chunk.track, chunk.index, chunk.start, chunk.seconds) == ("them", 3, 60.0, 30.0)
    assert chunk.path.endswith("them-0003.wav")
    recording = by_type["meeting_recording"]
    assert recording.on and recording.tracks == ("me",) and "System Audio Recording" in recording.error
    assert by_type["meeting_toggle"] == ev.MeetingToggle(False)


@pytest.mark.parametrize("bad", [
    {"type": "meeting_chunk", "id": "m", "track": "both", "index": 1, "path": "x", "start": 0, "seconds": 30},
    {"type": "meeting_chunk", "id": "m", "track": "me", "index": 0, "path": "x", "start": 0, "seconds": 30},
    {"type": "meeting_recording", "id": "m", "on": True, "tracks": "me"},
])
def test_bad_meeting_commands_are_refused(bad):
    with pytest.raises(ev.ProtocolError):
        ev.parse_command(bad)


def test_conversation_commands_parse_into_their_values():
    assert ev.parse_command({"type": "text", "text": "and then?", "conversation": "c-1"}) == \
        ev.TextInput("and then?", True, "c-1")
    assert ev.parse_command({"type": "text", "text": "hi"}).conversation == ""
    assert ev.parse_command({"type": "get_conversations"}) == ev.GetConversations("")
    assert ev.parse_command({"type": "open_conversation", "id": " c-1 "}) == ev.OpenConversation("c-1")
    assert ev.parse_command({"type": "search_conversations", "query": "  the  dentist "}) == \
        ev.SearchConversations("the dentist")
    assert ev.parse_command({"type": "rename_conversation", "id": "c-1", "title": "Trip"}) == \
        ev.RenameConversation("c-1", "Trip")
    for bad in ({"type": "open_conversation", "id": " "}, {"type": "rename_conversation", "id": "c-1", "title": ""}):
        with pytest.raises(ev.ProtocolError):
            ev.parse_command(bad)


def test_fixture_headers_and_entries_decode_into_the_brains_types():
    from milo.core.conversations import ConversationInfo
    from milo.core.types import TranscriptEntry

    (listing,) = [m for m in FIXTURE["brain_to_app"] if m["type"] == "conversations"]
    for header in listing["conversations"]:
        assert ConversationInfo.from_dict(header).to_dict() == header
    (history,) = [m for m in FIXTURE["brain_to_app"] if m["type"] == "history"]
    for entry in history["entries"]:
        assert TranscriptEntry.from_dict(entry).to_dict() == entry


def test_usage_command_takes_a_span_of_whole_days():
    assert ev.parse_command({"type": "get_usage"}) == ev.GetUsage(30)
    assert ev.parse_command({"type": "get_usage", "span": 7}) == ev.GetUsage(7)
    for span in (0, 367, 7.5, True, "30"):
        with pytest.raises(ev.ProtocolError):
            ev.parse_command({"type": "get_usage", "span": span})
