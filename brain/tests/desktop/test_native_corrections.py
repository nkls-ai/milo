from dataclasses import replace

import pytest

from milo.desktop.corrections import CorrectionObserver, correction_pairs, distance
from milo.desktop.native import Focus, writable


class Words:
    def is_word(self, word):
        return word.casefold() in {"their", "there", "cat", "car", "the", "big", "huge"}


@pytest.mark.parametrize("pasted,edited,expected", [
    ("I use Cloud Code every day.", "I use Claude Code every day.", [("Cloud Code", "Claude Code")]),
    ("Hi Nicholas, thanks for the notes.", "Hi Niklas, thanks for the notes.", [("Nicholas", "Niklas")]),
    ("Ask Anna and Nicholas Smith.", "Ask Anna and Niklas Smith.", [("Nicholas Smith", "Niklas Smith")]),
    ("Tell Nicholas the Cloud Code demo is on teh list.", "Tell Niklas the Claude Code demo is on the list.",
     [("Nicholas", "Niklas"), ("Cloud Code", "Claude Code"), ("teh", "the")]),
    ("Thanks Nicholas", "Thanks Niklas, see you soon", [("Nicholas", "Niklas")]),
    ("Nicholas said yes", "So Niklas said yes", [("Nicholas", "Niklas")]),
    ("push it to github today", "push it to GitHub today", [("github", "GitHub")]),
    ("ask milo now", "ask Milo now", [("milo", "Milo")]),
    ("on my Mac Book", "on my MacBook", [("Mac Book", "MacBook")]),
    ("we met and the plan is set", "we met. The plan is set", []),
    ("the plan is set", "The plan is set", []),
    ("Okay. The plan is set", "Okay, the plan is set", []),
    ("Let's meet at the station tomorrow morning", "Can we do lunch on Friday instead", []),
    ("See you at noon", "See you at noon. Also bring the cake, Claude", []),
    ("First thing. Second thing about Nicholas.", "First thing.", []),
    ("It is a big deal", "It is a huge deal", []),
    ("I think their right", "I think there right", []),
    ("the cat is here", "the car is here", []),
    ("See you on Monday", "See you on Sunday", []),
    ("meet at 15 sharp", "meet at 16 sharp", []),
    ("teh plan", "the plan", [("teh", "the")]),
    ("Hello Claude Code", "Hello, Claude Code!", []),
])
def test_small_fixes_follow_existing_mac_rules(pasted, edited, expected):
    assert correction_pairs(pasted, edited, Words()) == expected


def test_distance_counts_a_neighbor_swap_once():
    assert distance("teh", "the") == 1
    assert distance("cloud", "claude") == 2


def test_long_words_are_bounded_before_edit_distance_is_computed():
    assert correction_pairs("x" * 12000, "y" * 12000, Words()) == []


def setup():
    now = [0.0]
    observer = CorrectionObserver(writable, words=Words(), clock=lambda: now[0])
    before = Focus("field", 987654, "Editor", role="text field", editable=True, text="Dear Anna, ")
    text = "I use Cloud Code daily."
    observer.pasted(before, text)
    landed = replace(before, text=before.text + text)
    now[0] = 0.4
    observer.poll(landed)
    return observer, before, landed, now


def test_only_pairs_are_emitted_when_focus_leaves_the_watched_field():
    observer, before, landed, now = setup()
    observer.poll(replace(landed, text=landed.text.replace("Cloud", "Claude")))
    assert observer.take() == []
    observer.poll(None)
    assert observer.take() == [("Cloud Code", "Claude Code")]
    assert observer.take() == []


def test_watch_expires_and_releases_the_field_contents():
    observer, before, landed, now = setup()
    observer.poll(replace(landed, text=landed.text.replace("Cloud", "Claude")))
    now[0] = 46
    observer.poll(landed)
    assert observer.take() == [("Cloud Code", "Claude Code")]
    assert not observer.active and observer._watch is None


def test_turning_learning_off_discards_pending_and_watched_contents():
    observer, before, landed, now = setup()
    observer.poll(replace(landed, text=landed.text.replace("Cloud", "Claude")))
    observer.enable(False)
    observer.poll(None)
    assert observer.take() == [] and not observer.active


def test_changing_an_anchor_does_not_learn_a_different_span():
    observer, before, landed, now = setup()
    observer.poll(replace(landed, text=landed.text.replace("Dear Anna,", "Hello,")))
    observer.poll(None)
    assert observer.take() == []


def test_initial_read_must_prove_the_exact_inserted_span():
    observer = CorrectionObserver(writable, clock=lambda: 1)
    before = Focus("f", 987654, "Editor", editable=True, text="same original")
    observer.pasted(before, "Cloud Code")
    observer.clock = lambda: 2
    observer.poll(replace(before, text="Cloud Code somewhere else and changed original"))
    assert not observer.active and observer.take() == []


@pytest.mark.parametrize("changes", [{"secure": True}, {"app": "PowerShell"}, {"editable": False}])
def test_sensitive_fields_are_never_watched(changes):
    observer = CorrectionObserver(writable)
    before = Focus("f", 987654, "Editor", editable=True, text="")
    observer.pasted(replace(before, **changes), "Cloud Code")
    assert not observer.active


def test_adjacent_streaming_pastes_join_one_watch():
    observer, before, landed, now = setup()
    edited = replace(landed, text=landed.text.replace("Cloud", "Claude"))
    observer.poll(edited)
    observer.pasted(edited, " Thanks Nicholas.")
    second = replace(edited, text=edited.text + " Thanks Nicholas.")
    now[0] += 0.4
    observer.poll(second)
    observer.poll(replace(second, text=second.text.replace("Nicholas", "Niklas")))
    observer.poll(None)
    assert observer.take() == [("Cloud Code", "Claude Code"), ("Nicholas", "Niklas")]


def test_pastes_before_the_first_read_are_observed_together():
    now = [0]
    observer = CorrectionObserver(writable, words=Words(), clock=lambda: now[0])
    before = Focus("f", 987654, "Editor", editable=True, text="")
    observer.pasted(before, "Hi Nicholas,")
    observer.pasted(replace(before, text="Hi Nicholas,"), " thanks Nicholas.")
    now[0] = 0.4
    combined = replace(before, text="Hi Nicholas, thanks Nicholas.")
    observer.poll(combined)
    observer.poll(replace(combined, text=combined.text.replace("Nicholas", "Niklas")))
    observer.poll(None)
    assert observer.take() == [("Nicholas", "Niklas")]


def test_automated_edit_cancels_learning_without_learning_its_words():
    observer, before, landed, now = setup()
    observer.poll(replace(landed, text=landed.text.replace("Cloud", "Claude")))
    observer.cancel()
    observer.poll(None)
    assert observer.take() == [] and not observer.active
