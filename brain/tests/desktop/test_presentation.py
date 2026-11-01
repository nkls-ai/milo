"""The window's and the overlay's decisions, without Qt: ports of the Mac's MiloModel, Presence, TranscriptModel,
SpeechReveal, WindowRoute and MarkdownBlocks tests."""
from datetime import date, datetime

from milo.desktop.presentation import markdown, sidebar, thread
from milo.desktop.presentation.clock import ManualScheduler
from milo.desktop.presentation.milo import CAUGHT_BEAT, MiloState, bubble_duration
from milo.desktop.presentation.presence import Presence, hide_after
from milo.desktop.presentation.route import Page, Route
from milo.desktop.presentation.speech_reveal import SpeechReveal
from milo.desktop.presentation.transcript import LIMIT, Change, Transcript


def milo():
    clock = ManualScheduler()
    changes = []
    model = MiloState(clock, clock.clock, changes.append)
    model.set_connected(True)
    changes.clear()
    return model, clock, changes


# ---- the ear and the bubble (MiloModel)

def test_press_hold_release_and_the_beat_ends():
    model, clock, _ = milo()
    model.ear_event("armed", "talk")
    assert model.voice_phase.kind == "armed"
    model.ear_event("open", "talk")
    assert model.voice_phase.kind == "listening"
    model.ear_event("caught", "talk")
    assert model.voice_phase.kind == "caught"
    clock.advance(CAUGHT_BEAT - 0.01)
    assert model.ear is not None
    clock.advance(0.01)
    assert model.ear is None and model.voice_phase is None


def test_a_new_press_during_the_beat_is_not_cut_short():
    model, clock, _ = milo()
    model.ear_event("armed", "talk")
    model.ear_event("caught", "talk")
    clock.advance(0.3)
    model.ear_event("armed", "dictate")
    clock.advance(CAUGHT_BEAT)
    assert model.ear.kind == "armed" and model.ear.mode == "dictate"


def test_the_bubble_steps_aside_while_recording_and_comes_back():
    model, _, _ = milo()
    model.show("Done, it's in your Downloads.")
    model.ear_event("armed", "talk")
    assert model.voice_phase.recording
    model.ear_event("cancelled", "talk")
    assert model.voice_phase is None and model.bubble


def test_the_level_changes_only_the_level():
    model, _, changes = milo()
    for value in (0.1, 0.4, 0.4, 0.2):
        model.apply({"type": "level", "value": value})
    assert changes == [{"level"}] * 3  # the repeat is dropped


def test_bubble_hides_after_its_time_unless_speaking_or_asking():
    model, clock, _ = milo()
    model.apply({"type": "bubble", "text": "Hi there."})
    clock.advance(bubble_duration("Hi there.") + 0.01)
    assert model.bubble == ""
    model.apply({"type": "state", "state": "speaking"})
    model.apply({"type": "bubble", "text": "A long answer."})
    clock.advance(30)
    assert model.bubble == "A long answer."
    model.apply({"type": "confirm", "id": "q", "question": "Go?"})
    model.apply({"type": "state", "state": "idle"})
    clock.advance(30)
    assert model.bubble and model.question["id"] == "q"
    model.apply({"type": "confirm_done", "id": "q", "answer": "yes"})
    clock.advance(30)
    assert model.bubble == "" and model.question is None


def test_listening_clears_the_last_answer_and_level_drops_when_quiet():
    model, _, _ = milo()
    model.apply({"type": "bubble", "text": "Earlier."})
    model.apply({"type": "heard", "text": "what"})
    model.apply({"type": "state", "state": "listening"})
    model.apply({"type": "level", "value": 0.5})
    assert model.bubble == "" and model.heard == "" and model.level == 0.5
    model.apply({"type": "partial", "text": "what's on"})
    model.apply({"type": "state", "state": "transcribing"})
    assert model.partial == "what's on" and model.level == 0
    model.apply({"type": "state", "state": "thinking"})
    assert model.partial == ""


def test_thinking_says_so_when_it_takes_long():
    model, clock, changes = milo()
    model.apply({"type": "state", "state": "thinking"})
    assert model.hint == "Thinking"
    changes.clear()
    clock.advance(7)
    assert model.hint == "Still on it" and {"hint"} in changes
    clock.advance(20)
    assert model.hint == "Taking a while"
    model.apply({"type": "state", "state": "speaking"})
    assert model.thinking_since is None


def test_undo_goes_with_the_line_that_says_what_the_task_did():
    model, _, _ = milo()
    model.apply({"type": "undo_points", "points": [{"id": "t1", "title": "Red", "state": "ready",
                                                    "said": "Done: every cell of Book2 is red now."}]})
    model.show("Done: every cell")
    assert model.bubble_action == {"kind": "undo", "title": "Undo", "id": "t1"}
    model.apply({"type": "undo_points", "points": [{"id": "t1", "state": "undoing", "said": ""}]})
    assert model.bubble_action is None


def test_copy_is_offered_for_text_milo_kept():
    model, clock, _ = milo()
    model.offer_copy("Hi Anna")
    model.show("It's in my window.")
    assert model.bubble_action["kind"] == "copy" and model.bubble_action["text"] == "Hi Anna"
    model.show("It's in my window. Copy it from there.")
    assert model.bubble_action["kind"] == "copy"
    model.offer_copy("old")
    clock.advance(31)
    model.show("Something else.")
    assert model.bubble_action is None


def test_pasted_shows_for_a_beat_after_dictation():
    model, clock, _ = milo()
    model.pasted_text("   ")
    assert not model.pasted
    model.pasted_text("Hello")
    assert model.voice_phase.kind == "pasted"
    clock.advance(1.5)
    assert model.voice_phase is None


def test_a_lost_brain_leaves_no_question_helper_or_speech():
    model, _, _ = milo()
    model.apply({"type": "state", "state": "speaking"})
    model.apply({"type": "helpers", "helpers": [{"id": "h", "status": "working"}]})
    model.apply({"type": "confirm", "id": "q", "question": "Go?"})
    model.set_connected(False)
    assert model.state == "idle" and not model.helpers and model.question is None
    assert model.voice_phase.kind == "offline"


def test_celebrate_and_nudge():
    model, _, _ = milo()
    calls = []
    model.on_celebrate = lambda: calls.append("celebrate")
    model.on_nudge = lambda: calls.append("nudge")
    model.apply({"type": "action_done", "kind": "event", "title": "Dentist"})
    model.apply({"type": "confirm", "id": "q", "question": "Go?"})
    assert calls == ["celebrate", "nudge"]


def test_working_caption_follows_the_hands_only():
    model, _, _ = milo()
    model.apply({"type": "hands_session", "on": True})
    model.apply({"type": "activity", "task_id": "t", "step": {"id": "item_1", "title": "Worker", "status": "running"}})
    assert model.working_step == ""
    model.apply({"type": "activity", "task_id": "t", "step": {"id": "hands_3", "title": "Typing", "status": "running"}})
    assert model.working_step == "Typing"
    model.apply({"type": "hands_session", "on": False})
    assert model.working_step == ""


# ---- presence

def test_he_leaves_after_the_wait_and_comes_back_when_needed():
    model, clock, _ = milo()
    presence = Presence(clock, lambda: model.needed)
    clock.advance(16)
    assert not presence.shown
    model.apply({"type": "bubble", "text": "Hi"})
    presence.check()
    assert presence.shown
    clock.advance(bubble_duration("Hi") + 0.1)
    presence.check()
    assert presence.shown
    clock.advance(15.1)
    assert not presence.shown


def test_pointer_and_hide_after_zero_keep_him():
    clock = ManualScheduler()
    presence = Presence(clock, lambda: False)
    resting = [True]
    presence.pointing = lambda: resting[0]
    clock.advance(16)
    assert presence.shown
    resting[0] = False
    clock.advance(3.1)
    assert not presence.shown
    presence.hide_after = None
    assert presence.shown
    clock.advance(100)
    assert presence.shown
    assert hide_after(0) is None and hide_after("x") == 15 and hide_after(30) == 30


def test_summon_restarts_the_wait():
    clock = ManualScheduler()
    presence = Presence(clock, lambda: False)
    clock.advance(10)
    presence.summon()
    clock.advance(10)
    assert presence.shown
    clock.advance(6)
    assert not presence.shown


# ---- the transcript

def entry(i, kind="milo", conversation="c1", **extra):
    return {"id": f"e{i}", "ts": f"2026-10-30T09:{i:02d}:00", "kind": kind, "text": f"line {i}",
            "conversation": conversation, **extra}


def test_reply_delta_updates_one_row():
    changes = []
    t = Transcript(changes.append)
    t.apply({"type": "history", "entries": [entry(1, "user"), entry(2, done=False)]})
    changes.clear()
    t.apply({"type": "reply_delta", "id": "e2", "text": " more"})
    assert t.entries[1]["text"] == "line 2 more"
    assert changes == [Change("update", "c1", 1)]
    t.apply({"type": "reply_delta", "id": "new", "text": "Sure"})
    assert changes[-1] == Change("insert", "c1", 2) and t.entries[-1]["kind"] == "milo"


def test_a_new_user_turn_in_an_unknown_conversation_starts_the_next_one():
    t = Transcript()
    t.apply({"type": "history", "entries": [entry(1, "user")]})
    t.apply({"type": "entry", "entry": entry(2, "user", conversation="c2")})
    assert t.current == "c2" and [e["id"] for e in t.entries] == ["e2"]
    assert [e["id"] for e in t.entries_of("c1")] == ["e1"]


def test_opened_conversation_and_activity_steps():
    t = Transcript()
    t.apply({"type": "conversations", "conversations": [{"id": "c1", "last": "2026-10-30T09:00:00"}],
             "current": "c1"})
    t.apply({"type": "conversation", "id": "c9", "info": {"id": "c9", "last": "2026-10-29T09:00:00"},
             "entries": [entry(3, "task", conversation="c9")]})
    t.apply({"type": "activity", "task_id": "e3", "step": {"id": "s1", "title": "Reading", "status": "running"}})
    t.apply({"type": "activity", "task_id": "e3", "step": {"id": "s1", "title": "Reading", "status": "done"}})
    task, info = t.task("e3")
    assert task["steps"] == [{"id": "s1", "title": "Reading", "status": "done"}] and info["id"] == "c9"


def test_the_brain_copy_keeps_what_streams_now():
    t = Transcript()
    t.apply({"type": "history", "entries": [entry(1, "user")]})
    t.apply({"type": "reply_delta", "id": "live", "text": "streaming"})
    t.apply({"type": "conversation", "id": "c1", "info": {"id": "c1"}, "entries": [entry(1, "user")]})
    assert [e["id"] for e in t.entries] == ["e1", "live"]


def test_entries_are_capped():
    changes = []
    t = Transcript(changes.append)
    t.apply({"type": "history", "entries": [entry(i % 60) | {"id": f"x{i}"} for i in range(LIMIT)]})
    t.apply({"type": "entry", "entry": entry(1) | {"id": "last"}})
    assert len(t.entries) == LIMIT and changes[-1] == Change("trim", "c1", 1)


# ---- the route, the sidebar, the thread

def test_route_slides_by_depth_and_goes_back():
    route = Route()
    route.go(Page("live"))
    assert route.forward
    route.go(Page("task", "t1"))
    route.go_back()
    assert route.page == Page("live") and not route.forward
    route.go_back()
    assert route.page == Page("today")
    assert not route.go_back()
    assert Route(Page("live")).conversation("c1") == "c1"


NOW = datetime(2026, 10, 30, 12, 0)


def test_sidebar_groups_by_day_with_a_thread_and_beads():
    conversations = [
        {"id": "a", "title": "Photos", "last": "2026-10-30T09:14:10", "tasks": [{"status": "running", "title": "Rename"}]},
        {"id": "b", "title": "Train", "last": "2026-10-30T07:41:12", "via": ["message"], "preview": "On time."},
        {"id": "c", "title": "Report", "kind": "routine", "last": "2026-10-27T09:03:40"},
        {"id": "d", "title": "Old", "last": "2026-08-01T10:00:00", "turns": 1},
    ]
    rows = sidebar.rows(conversations, "b", NOW)
    assert [r["section"] for r in rows] == ["Today", "Today", "This week", "August"]
    assert rows[0]["bead"] == "working" and rows[0]["subtitle"] == "Working on “Rename”…"
    assert rows[1]["bead"] == "live" and rows[1]["mark"] == "phone" and rows[1]["time"] == "7:41"
    assert rows[0]["first"] and not rows[0]["last"] and rows[1]["last"]
    assert rows[2]["time"] == "Tue" and rows[2]["subtitle"] == "Ran on its schedule"
    assert rows[3]["time"] == "1 Aug" and rows[3]["subtitle"] == "1 message"


def test_meeting_row_says_it_takes_notes():
    info = {"id": "m", "kind": "meeting", "title": "Sync", "last": "2026-10-30T09:00:00"}
    meeting = {"id": "x", "phase": "recording", "conversation": "m"}
    assert sidebar.subtitle(info, meeting) == ("Taking notes now", True)


def test_header_subtitle():
    info = {"id": "a", "started": "2026-10-30T09:12:00", "turns": 6, "tasks": [{"id": "t"}], "via": ["message"]}
    assert sidebar.header(info, NOW)["subtitle"] == "Today 9:12 · 6 turns · 1 task · from your phone"


def test_thread_times_gaps_days_and_pending():
    a, b = entry(1, "user"), entry(1, "milo")
    assert thread.shows_time(a, None) and not thread.shows_time(b, a)
    assert thread.gap(b, a) == 8 and thread.gap(a, b) == 18 and thread.gap(a, None) == 0
    assert thread.day_heading(a, None, date(2026, 10, 30)) == "Today"
    assert thread.day_heading(b, a, date(2026, 10, 30)) == ""
    assert thread.day_heading(a, None, date(2026, 11, 2)) == "Friday, 30 October"
    assert thread.pending("thinking", {"kind": "milo", "done": False}) == ""
    assert thread.pending("thinking", {"kind": "user"}) == "Thinking…"
    assert thread.pending("idle", None) == ""


# ---- speech reveal and markdown

def test_words_keep_pace_with_his_voice():
    reveal = SpeechReveal()
    reveal.show("Hello there, how are you?", speaking=True, at=0)
    cut = reveal.cut(0.0)
    assert cut.shown == 0
    middle = reveal.cut(0.6)
    assert 0 < middle.shown + middle.fresh < len(reveal.text)
    assert reveal.text[middle.shown + middle.fresh:][:1] in (" ", "")
    reveal.show("Hello there, how are you? I am fine, thanks.", speaking=True, at=2.0)
    assert reveal.settled == len("Hello there, how are you?")
    reveal.finish()
    assert reveal.done(2.0)
    quiet = SpeechReveal()
    quiet.show("Muted answer", speaking=False, at=0)
    assert quiet.done(0)


def test_markdown_blocks_and_safe_inline():
    blocks = markdown.parse("# Notes\n\nFirst line\nsecond line\n\n- one\n  more\n- [x] done\n1. first\n> quoted\n---\n```\ncode\n```")
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["heading", "paragraph", "bullet", "todo", "numbered", "quote", "rule", "code"]
    assert blocks[1]["text"] == "First line second line" and blocks[2]["text"] == "one more"
    assert blocks[3]["done"] and blocks[4]["number"] == 1 and blocks[0]["gap"] == 0
    rich = markdown.inline("**bold** <script> [x](https://evil) [t](transcript.md) `a<b`")
    assert "<b>bold</b>" in rich and "&lt;script&gt;" in rich and "evil" not in rich
    assert '<a href="transcript.md"' in rich and "<code>a&lt;b</code>" in rich
    assert markdown.has_markup("- a list") and not markdown.has_markup("Just words.")

