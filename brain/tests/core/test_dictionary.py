"""The dictionary's format and the rules for when a learned fix replaces text (ADR 21)."""

import pytest

from milo.core.dictionary import Entries, Fix, Replacements, looks_like_a_name, parse, valid
from milo.core.events import DictationFixed, ProtocolError, parse_command


def test_parse_reads_words_and_fixes_and_skips_the_rest():
    entries = parse("""# Dictionary

Some explanation with -> an arrow that is not an item.

## Words
Names Whisper should spell right.

- Milo
- `Niklas Dobberstein`
- Milo

## Fixes
`- heard -> meant`: explanation.

- Cloud Code -> Claude Code (seen 1)
- teh → the (seen 3, learned)
- GPT four -> GPT-4
- broken line without arrow
- same -> same
""")
    assert entries.words == ("Milo", "Niklas Dobberstein")
    assert entries.fixes == (Fix("Cloud Code", "Claude Code", 1), Fix("teh", "the", 3), Fix("GPT four", "GPT-4"))


def test_a_fix_outside_the_fixes_section_still_counts_but_a_word_needs_its_section():
    entries = parse("- Anna\n## Words\n- Cloud -> Claude\n")
    assert entries.words == ()
    assert entries.fixes == (Fix("Cloud", "Claude"),)


@pytest.mark.parametrize("fix, applies", [
    (Fix("Cloud Code", "Claude Code", 1), True),  # a name: one fix is enough
    (Fix("Nicholas", "Niklas", 1), True),
    (Fix("cloud", "Claude", 1), False),  # one lowercase word: likely an ordinary word elsewhere
    (Fix("cloud", "Claude", 2), True),
    (Fix("teh", "the", 1), False),  # no capital: not a name
    (Fix("teh", "the", 2), True),
    (Fix("github", "GitHub", 1), False),
    (Fix("teh", "the"), True),  # the user wrote it
])
def test_when_a_fix_applies(fix, applies):
    assert fix.applies is applies


def test_looks_like_a_name_needs_a_capital_and_not_one_lowercase_word():
    assert looks_like_a_name("mac book", "MacBook")
    assert not looks_like_a_name("macbook", "MacBook")
    assert not looks_like_a_name("Mac Book", "mac book")


@pytest.mark.parametrize("heard, meant, ok", [
    ("Cloud Code", "Claude Code", True),
    ("a b c d e", "x", False),  # five words: a rewrite, not a fix
    ("x" * 61, "y", False),
    ("Cloud", "Cloud", False),
    ("Cloud ", " Cloud", False),
    ("", "Claude", False),
    ("Cloud", "Claude\nCode", False),
    ("Cloud", "a -> b", False),
])
def test_valid(heard, meant, ok):
    assert valid(heard, meant) is ok


def test_vocabulary_puts_the_users_words_first_then_the_most_seen():
    entries = Entries(("Milo",), (Fix("teh", "the", 2), Fix("Cloud Code", "Claude Code", 5), Fix("Nik", "Niklas"),
                                  Fix("Milow", "Milo", 1)))
    assert entries.vocabulary() == ["Milo", "Niklas", "Claude Code", "the"]


def test_replacements_match_whole_words_only():
    r = Replacements((Fix("Cloud Code", "Claude Code", 1),))
    assert r.apply("I use Cloud Code daily.") == "I use Claude Code daily."
    assert r.apply("I use Cloud  Code, and Cloud Code.") == "I use Claude Code, and Claude Code."
    assert r.apply("The Cloud Codex is new.") == "The Cloud Codex is new."
    assert r.apply("the cloud code") == "the cloud code", "a different case is a different word"


def test_a_lowercase_fix_also_matches_at_a_sentence_start():
    r = Replacements((Fix("teh", "the", 2),))
    assert r.apply("Teh cat sat on teh mat.") == "The cat sat on the mat."
    assert r.apply("tehran") == "tehran"


def test_only_fixes_that_apply_replace():
    r = Replacements((Fix("cloud", "Claude", 1),))
    assert not r
    assert r.apply("the cloud") == "the cloud"


def test_longer_fixes_go_first():
    r = Replacements((Fix("Code", "code", 2), Fix("Cloud Code", "Claude Code", 1)))
    assert r.apply("Cloud Code") == "Claude Code"


def test_dictation_fixed_parses_pairs_and_refuses_anything_else():
    assert parse_command({"type": "dictation_fixed", "fixes": [{"heard": "a", "meant": "b"}]}) == \
        DictationFixed((("a", "b"),))
    for bad in ({"fixes": "a -> b"}, {"fixes": ["a"]}, {"fixes": [{"heard": "a"}]}, {}):
        with pytest.raises(ProtocolError):
            parse_command({"type": "dictation_fixed", **bad})
