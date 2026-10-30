from datetime import datetime

import pytest

from milo.core.types import Emotion
from milo.services.reply_stream import ReplyParser, parse_reminder


def stream(*deltas: str) -> tuple[ReplyParser, list[str]]:
    """Feed deltas one by one; return the parser and what each feed() (then finish()) released."""
    parser = ReplyParser()
    out = [parser.feed(d) for d in deltas]
    out.append(parser.finish())
    return parser, out


def spoken(*deltas: str) -> str:
    return "".join(stream(*deltas)[1])


def every_split(text: str) -> list[tuple[str, str]]:
    """The text as two deltas, cut at every position, to catch tags split anywhere."""
    return [(text[:i], text[i:]) for i in range(len(text) + 1)]


def test_emotion_tag_opens_the_reply_and_is_not_spoken():
    parser, out = stream("[happy] Hello there.")
    assert parser.emotion is Emotion.HAPPY
    assert "".join(out) == "Hello there."


def test_emotion_is_unknown_until_the_tag_closes():
    parser = ReplyParser()
    assert parser.feed("  [exc") == ""
    assert parser.emotion is None
    assert parser.feed("ited]Wow") == "Wow"
    assert parser.emotion is Emotion.EXCITED


def test_no_tag_means_neutral_and_the_text_is_spoken_at_once():
    parser = ReplyParser()
    assert parser.feed("Sure, ") == "Sure, "
    assert parser.emotion is Emotion.NEUTRAL


def test_unknown_emotion_word_is_neutral_and_dropped():
    parser, out = stream("[smug] Fine.")
    assert parser.emotion is Emotion.NEUTRAL and "".join(out) == "Fine."


def test_a_long_bracket_at_the_start_is_text_not_an_emotion():
    parser, out = stream("[this is not an emotion tag at all] ok")
    assert parser.emotion is Emotion.NEUTRAL
    assert "".join(out) == "[this is not an emotion tag at all] ok"


def test_finish_without_any_text_is_neutral_and_empty():
    parser, out = stream()
    assert parser.emotion is Emotion.NEUTRAL and out == [""]
    parser, out = stream("[sad]")
    assert parser.emotion is Emotion.SAD and "".join(out) == ""


@pytest.mark.parametrize("head, tail", every_split("[happy] Noted. <remember>Likes tea</remember> Bye."))
def test_remember_tag_split_anywhere_is_collected_and_never_spoken(head, tail):
    parser, out = stream(head, tail)
    assert "".join(out) == "Noted.  Bye."
    assert parser.remembers == ["Likes tea"]
    assert all("<" not in part and "remember" not in part for part in out)


@pytest.mark.parametrize("head, tail", every_split("[neutral] Ok <reminder>2026-10-30 09:00 Call mom</reminder>"))
def test_reminder_tag_split_anywhere_parses_the_due_time(head, tail):
    parser, out = stream(head, tail)
    assert "".join(out) == "Ok "
    assert parser.reminders == [(datetime(2026, 10, 30, 9, 0), "Call mom")]


def test_tags_arriving_character_by_character():
    text = "[thinking] On it. <task>Find the cheapest flight to Lisbon</task>"
    parser, out = stream(*text)
    assert "".join(out) == "On it. "
    assert parser.tasks == ["Find the cheapest flight to Lisbon"]
    assert parser.emotion is Emotion.THINKING


def test_text_after_a_partial_tag_start_is_held_back_until_it_cannot_be_a_tag():
    parser = ReplyParser()
    assert parser.feed("[happy] 3 <") == "3 "
    assert parser.feed("re") == ""
    assert parser.feed("d apples") == "<red apples"


def test_a_lone_less_than_is_spoken_at_the_end():
    assert spoken("[neutral] a <") == "a <"


def test_several_tags_and_case_insensitive_names():
    parser, out = stream("[happy] Done. <REMEMBER>Has a cat</Remember><remember>Has a cat</remember>",
                         "<task>  sort\n the  downloads </task>")
    assert "".join(out) == "Done. "
    assert parser.remembers == ["Has a cat", "Has a cat"], "dedup is the profile's job"
    assert parser.tasks == ["sort the downloads"]


def test_unclosed_tag_at_the_end_still_counts():
    parser, out = stream("[happy] Sure. <task>water the plants")
    assert "".join(out) == "Sure. "
    assert parser.tasks == ["water the plants"]


def test_stray_closing_tag_and_mid_reply_emotion_tags_are_dropped():
    assert spoken("[happy] Hi</task> there [sad] friend.") == "Hi there  friend."


def test_other_brackets_are_spoken():
    assert spoken("[neutral] Press [Enter] now") == "Press [Enter] now"


def test_markdown_noise_is_stripped():
    assert spoken("[happy] **Bold** and `code` # heading") == "Bold and code  heading"


def test_empty_tags_are_ignored():
    parser, _ = stream("[happy] Hi <remember> </remember><task></task>")
    assert parser.remembers == [] and parser.tasks == []


def test_malformed_reminders_are_ignored():
    parser, _ = stream("[happy] ok <reminder>tomorrow at nine call mom</reminder>"
                       "<reminder>2026-02-30 09:00 impossible</reminder>")
    assert parser.reminders == []


def test_spoken_accumulates_everything_released():
    parser, out = stream("[happy] One, ", "two <remember>x</remember>three.")
    assert parser.spoken == "".join(out) == "One, two three."


@pytest.mark.parametrize("content, expected", [
    ("2026-10-30 09:00 Call mom", (datetime(2026, 10, 30, 9, 0), "Call mom")),
    ("2026-10-30T9:05 Stretch", (datetime(2026, 10, 30, 9, 5), "Stretch")),
    ("2026-10-30 09:00", None),
    ("30.10.2026 09:00 Call", None),
    ("2026-13-01 09:00 Call", None),
])
def test_parse_reminder(content, expected):
    assert parse_reminder(content) == expected
