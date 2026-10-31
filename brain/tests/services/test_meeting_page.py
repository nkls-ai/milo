"""What the app shows of meeting notes: the status for the capsule and the menu bar, the lines as they are
transcribed, the notes for the meeting's page, pausing, and the per-app answers to "Should I take notes?"."""

from __future__ import annotations

import asyncio

from milo.core.events import (CallEnded, CallStarted, MeetingLines, MeetingNotesReady, MeetingPause, MeetingStatus,
                              MeetingToggle, OpenMeeting)
from milo.services.meetings import CONSENT, QUESTION, WRITING, MeetingOptions
from milo.services.transcript import Transcript
from tests.fakes import MemoryConversations
from tests.meeting_fakes import Script, word
from tests.services.stack import Stack, settle
from tests.services.test_meetings import Rig, until


def statuses(rig: Rig) -> list[MeetingStatus]:
    return rig.s.sink.of(MeetingStatus)


def shown_lines(rig: Rig) -> list[dict]:
    """The lines as the app holds them after every meeting_lines so far."""
    held: dict = {}
    for event in rig.s.sink.of(MeetingLines):
        if event.reset:
            held = {}
        for line in event.lines:
            held[(line["at"], line["me"])] = line
    return sorted(held.values(), key=lambda line: line["at"])


def test_the_status_follows_recording_pausing_and_writing_the_notes(tmp_path):
    rig = Rig(tmp_path, Script.conversation(["Anna", "me"], lines=12))

    async def go():
        rig.service.handle(CallStarted("Zoom"))
        await rig.answer(True)
        first = statuses(rig)[-1]
        assert (first.id, first.phase, first.title, first.app) == (rig.id, "recording", "Zoom call", "Zoom")
        assert first.consent == CONSENT and first.started.startswith(str(rig.s.clock.now().date()))
        rig.s.clock.advance(seconds=95)
        rig.service.handle(MeetingPause(True))
        assert statuses(rig)[-1].phase == "paused" and statuses(rig)[-1].elapsed == 95
        rig.service.handle(MeetingPause(True))  # twice is once
        assert [s.phase for s in statuses(rig)].count("paused") == 1
        rig.s.clock.advance(seconds=5)
        rig.service.handle(MeetingPause(False))
        assert statuses(rig)[-1].phase == "recording"
        stopping = asyncio.create_task(rig.service.toggle(False))  # Stop on the capsule
        await until(lambda: len(rig.records()) == 2)
        assert statuses(rig)[-1].phase == "writing" and statuses(rig)[-1].step == WRITING[0]
        rig.s.clock.advance(seconds=30)
        await rig.finish()
        await stopping

    asyncio.run(go())
    writing = [s for s in statuses(rig) if s.phase == "writing"]
    assert [s.step for s in writing] == [WRITING[0], WRITING[1], WRITING[2]]
    assert all(s.elapsed == 100 for s in writing), "the clock stops with the recording"
    done = [s for s in statuses(rig) if s.phase == "done"]
    assert len(done) == 1 and done[-1].elapsed == 100 and done[-1].step.startswith("Your notes from")
    assert rig.service.status_event() == MeetingStatus(""), "nothing goes on any more"
    assert rig.s.sink.of(MeetingNotesReady)[-1].id == rig.id


def test_lines_stream_to_the_app_once_each_as_passes_finish(tmp_path):
    script = Script.conversation(["Anna", "me", "Sam"], lines=24)
    rig = Rig(tmp_path, script)

    async def go():
        await rig.service.toggle(True)
        rig.deliver(upto=40)
        await until(lambda: min(rig.store.progress(rig.id).values(), default=0) > 20)
        early = len(shown_lines(rig))
        assert early > 0, "the first lines show while the call goes on"
        await rig.finish()
        return early

    early = asyncio.run(go())
    lines = shown_lines(rig)
    sent = [line for e in rig.s.sink.of(MeetingLines) if not e.reset for line in e.lines]
    assert len(sent) == len(lines) > early, "each line is sent once"
    assert {line["who"] for line in lines} >= {"You", "Speaker 1", "Speaker 2"}
    assert all(line["me"] == (line["who"] == "You") for line in lines)
    assert [line["at"] for line in lines] == sorted(line["at"] for line in lines)
    status = [s for s in statuses(rig) if s.phase == "recording"][-1]
    assert status.speakers[0] == "You" and "Speaker 1" in status.speakers


def test_naming_a_voice_sends_every_line_again_with_the_name(tmp_path):
    script = Script.conversation(["Anna", "me"], lines=10)
    rig = Rig(tmp_path, script)

    async def go():
        await rig.service.toggle(True)
        rig.deliver(upto=40)
        await until(lambda: any(l["who"] == "Speaker 1" for l in shown_lines(rig)))
        await rig.service.before_turn("Speaker 1 is Anna")
        rig.deliver()
        await rig.finish()

    asyncio.run(go())
    assert any(e.reset and e.lines for e in rig.s.sink.of(MeetingLines))
    assert {l["who"] for l in shown_lines(rig)} == {"You", "Anna"}


def test_a_paused_stretch_stays_out_of_the_notes(tmp_path):
    script = Script.conversation(["Anna", "me"], lines=8, gap=2.0)
    rig = Rig(tmp_path, script)
    paused = next(s for s in script.said if s.start > 20)

    async def go():
        await rig.service.toggle(True)
        rig.s.clock.advance(seconds=paused.start - 0.2)
        rig.service.pause(True)
        rig.s.clock.advance(seconds=paused.end - paused.start + 0.4)
        rig.service.pause(False)
        await rig.finish()

    asyncio.run(go())
    transcript = (rig.store.folder(rig.id) / "transcript.md").read_text()
    assert word(paused.line, 0) not in transcript and word(1, 0) in transcript
    assert all(word(paused.line, 0) not in l["text"] for l in shown_lines(rig))


def test_the_notes_page_has_the_markdown_the_sections_and_the_transcript(tmp_path):
    rig = Rig(tmp_path, Script.conversation(["Anna", "me"], lines=6), offers=True)

    async def go():
        await rig.service.toggle(True)
        await rig.finish()
        id = rig.id
        rig.s.sink.events.clear()
        rig.service.handle(OpenMeeting(id))
        rig.service.handle(OpenMeeting("../../etc"))
        rig.service.handle(OpenMeeting("2026-01-01-0000-nothing"))

    asyncio.run(go())
    lines = rig.s.sink.of(MeetingLines)
    assert lines[0].reset and lines[0].lines == [] and len(shown_lines(rig)) >= 6
    [page] = rig.s.sink.of(MeetingNotesReady)
    notes = (rig.store.folder(page.id) / "notes.md").read_text()
    assert page.markdown == notes and page.summary == "We moved the release by a week."
    assert page.decisions == ("Release on the 21st",)
    assert page.todos == ({"text": "Write to the customer", "owner": "", "due": "Friday", "mine": True, "added": False},
                          {"text": "Book the hotel", "owner": "Fred", "due": "", "mine": False, "added": False})
    assert page.reminders and page.mail and not page.mail_drafted and page.duration > 0
    assert page.folder == str(rig.store.folder(page.id)) and page.people


def test_the_meeting_is_one_conversation_from_start_to_notes(tmp_path):
    stack = Stack(confirm_timeout_s=2.0)
    transcript = Transcript(stack.ui, MemoryConversations(), stack.clock)
    rig = Rig(tmp_path, Script.conversation(["Anna", "me"], lines=4), stack=stack, transcript=transcript)

    async def go():
        await rig.service.toggle(True)
        conversation = statuses(rig)[-1].conversation
        assert conversation and transcript.info(conversation).kind == "meeting"
        assert transcript.info(conversation).source == f"meeting:{rig.id}"
        await rig.finish()
        return conversation

    conversation = asyncio.run(go())
    entries = [e for e in rig.s.sink.events if getattr(e, "type", "") == "entry"]
    assert {e.entry["conversation"] for e in entries} == {conversation}
    assert entries[-1].entry["text"] == "Notes from “Meeting”: We moved the release by a week."
    assert rig.s.sink.of(MeetingNotesReady)[-1].conversation == conversation


def test_always_for_an_app_is_remembered_and_takes_notes_without_asking_next_time(tmp_path):
    rig = Rig(tmp_path, Script.conversation(["Anna"], lines=1))
    remembered = []

    def remember(key, app):
        remembered.append((key, app))
        rig.service.options = MeetingOptions(**{**rig.service.options.__dict__, key: (app,)})

    rig.service.remember = remember

    async def go():
        rig.service.handle(CallStarted("Zoom"))
        await until(lambda: rig.questions() and rig.s.approvals.pending)
        question = rig.questions()[0]
        assert question.question == QUESTION
        assert [c["label"] for c in question.choices] == ["Take notes", "Not this time", "Always for Zoom",
                                                          "Never for Zoom"]
        assert rig.s.approvals.answer(question.id, True, choice="always")
        await until(lambda: rig.records())
        await rig.finish()
        rig.service.handle(CallEnded("Zoom"))
        await asyncio.sleep(0.1)
        rig.service.handle(CallStarted("zoom"))
        await until(lambda: len(rig.records()) >= 2)

    asyncio.run(go())
    assert remembered == [("always", "Zoom")]
    assert len(rig.questions()) == 1, "the second Zoom call starts without a question"


def test_never_for_an_app_is_remembered_and_never_asks_again(tmp_path):
    rig = Rig(tmp_path, Script.conversation(["Anna"], lines=1))
    remembered = []

    def remember(key, app):
        remembered.append((key, app))
        rig.service.options = MeetingOptions(never=(app,))

    rig.service.remember = remember

    async def go():
        rig.service.handle(CallStarted("WhatsApp"))
        await until(lambda: rig.questions() and rig.s.approvals.pending)
        assert rig.s.approvals.answer(rig.questions()[0].id, False, choice="never")
        await settle()
        rig.service.handle(CallEnded("WhatsApp"))
        await asyncio.sleep(0.1)
        rig.service.handle(CallStarted("WhatsApp"))
        await asyncio.sleep(0.1)

    asyncio.run(go())
    assert remembered == [("never", "WhatsApp")] and not rig.records() and len(rig.questions()) == 1


def test_a_newly_connected_app_hears_what_goes_on(tmp_path):
    rig = Rig(tmp_path, Script.conversation(["Anna"], lines=1))
    assert rig.service.status_event() == MeetingStatus("")

    async def go():
        await rig.service.toggle(True)
        assert rig.service.status_event().phase == "recording"
        rig.service.handle(MeetingToggle(False))
        await until(lambda: len(rig.records()) == 2)
        assert rig.service.status_event().phase == "writing"
        await rig.finish()

    asyncio.run(go())
