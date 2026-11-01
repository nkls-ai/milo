from milo.desktop.model import DesktopState, confirmation_answer
import pytest


def test_streamed_reply_replaces_final_entry_and_history_resets():
    model = DesktopState()
    model.apply({"type": "reply_delta", "id": "r", "text": "One "})
    model.apply({"type": "reply_delta", "id": "r", "text": "two"})
    assert model.entries["r"]["text"] == "One two"
    model.apply({"type": "entry", "entry": {"id": "r", "kind": "milo", "text": "One two."}})
    assert len(model.entries) == 1 and model.entries["r"]["text"] == "One two."
    model.apply({"type": "conversation", "id": "older", "entries": []})
    assert model.current == "older" and not model.entries


def test_confirmations_remain_until_brain_finishes_them():
    model = DesktopState()
    first = {"type": "confirm", "id": "first", "question": "Buy it?", "money": True}
    model.apply(first)
    model.apply({"type": "confirm", "id": "second", "question": "Do this?"})
    assert confirmation_answer(first, "yes") == {
        "type": "confirm_answer", "id": "first", "yes": True, "always": False, "choice": "yes"}
    assert set(model.confirmations) == {"first", "second"}
    model.apply({"type": "confirm_done", "id": "first"})
    assert list(model.confirmations) == ["second"]
    with pytest.raises(ValueError):
        confirmation_answer(first, "always")


def test_custom_choice_is_preserved_and_cannot_invent_permission():
    question = {"id": "q", "choices": [{"id": "once", "label": "This meeting"}]}
    answer = confirmation_answer(question, "once")
    assert answer["choice"] == "once" and not answer["always"] and not answer["yes"]
    with pytest.raises(ValueError):
        confirmation_answer(question, "yes")


def test_new_meeting_clears_old_transcript_but_pause_keeps_it():
    model = DesktopState()
    model.apply({"type": "meeting_status", "id": "m1", "phase": "recording"})
    model.apply({"type": "meeting_lines", "id": "m1", "lines": [{"text": "hello"}]})
    model.apply({"type": "meeting_status", "id": "m1", "phase": "paused"})
    assert len(model.meeting_lines) == 1
    model.apply({"type": "meeting_status", "id": "m2"})
    assert not model.meeting_lines
