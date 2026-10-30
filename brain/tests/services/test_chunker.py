from milo.services.chunker import MAX_CHARS, MIN_BUDGET, SpeechChunker


def pieces(*deltas: str, budget: int = MAX_CHARS) -> list[str]:
    """Feed every delta, take what is ready after each, then flush the rest as the final piece."""
    chunker = SpeechChunker()
    out = []
    for d in deltas:
        chunker.add(d)
        while (p := chunker.next(budget)) is not None:
            out.append(p)
    while (p := chunker.next(budget, final=True)) is not None:
        out.append(p)
    return out


def test_first_piece_goes_at_the_first_clause_with_three_words():
    chunker = SpeechChunker()
    chunker.add("Well, I think")
    assert chunker.next() is None
    chunker.add(" so, yes")
    assert chunker.next() == "Well, I think so,"


def test_first_piece_skips_boundaries_before_three_words():
    assert pieces("Sure! Let me check that for you. ", "It is nine.") == [
        "Sure! Let me check that for you.", "It is nine."]


def test_first_piece_after_eight_words_without_punctuation():
    chunker = SpeechChunker()
    chunker.add("one two three four five six seven eight")
    assert chunker.next() is None, "the eighth word may not be done"
    chunker.add(" nine")
    assert chunker.next() == "one two three four five six seven eight"
    assert chunker.next(final=True) == "nine"


def test_a_big_budget_takes_everything_up_to_the_furthest_boundary():
    chunker = SpeechChunker()
    chunker.add("Hi there you, this is one. This is two! And thr")
    assert chunker.next() == "Hi there you,"
    assert chunker.next(200) == "this is one. This is two!"
    assert chunker.next(200) is None, "waits for the rest of the sentence"
    assert chunker.next(200, final=True) == "And thr"


def test_a_small_budget_takes_the_boundary_that_fits():
    chunker = SpeechChunker()
    chunker.add("Okay then you, the first part goes right here, then comes a second part, and then the end. ")
    chunker.next()
    assert chunker.next(60) == "the first part goes right here, then comes a second part,"
    assert chunker.next(60) is None, "the sentence end needs the next word"
    assert chunker.next(60, final=True) == "and then the end."


def test_a_boundary_a_little_past_the_budget_beats_a_mid_clause_cut():
    chunker = SpeechChunker()
    chunker.add("Okay then you, the fridge moves the heat from inside to outside, ")
    chunker.next()
    assert chunker.next(50) == "the fridge moves the heat from inside to outside,"


def test_text_past_the_budget_without_a_boundary_cuts_on_a_space():
    chunker = SpeechChunker()
    chunker.add("Okay then you, " + "word " * 30)
    chunker.next()
    piece = chunker.next(60)
    assert piece is not None and len(piece) <= 60 and piece.endswith("word")


def test_the_budget_never_drops_below_the_minimum():
    chunker = SpeechChunker()
    chunker.add("Okay then you, alpha beta gamma delta epsilon zeta eta theta. Next")
    chunker.next()
    assert chunker.next(0) == "alpha beta gamma delta epsilon zeta eta theta.", f"{MIN_BUDGET} chars plus overshoot"


def test_a_sentence_end_waits_for_the_next_word():
    chunker = SpeechChunker()
    chunker.add("Hi there you, ")
    chunker.next()
    chunker.add("this is one.")
    assert chunker.next(200) is None
    chunker.add(" ")
    assert chunker.next(200) is None
    chunker.add("Next")
    assert chunker.next(200) == "this is one."


def test_decimals_and_abbreviations_do_not_split():
    assert pieces("Hello you all, ", "version 2.5 is out e.g. today. Nice", budget=MIN_BUDGET) == [
        "Hello you all,", "version 2.5 is out e.g. today.", "Nice"]


def test_pieces_never_exceed_the_cap_and_keep_every_word():
    text = "a b c d e f g h " + "y" * 10 + " " + "z " * 200
    out = pieces(text)
    assert out[0] == "a b c d e f g h"
    assert all(len(p) <= MAX_CHARS for p in out)
    assert " ".join(out).split() == text.split()


def test_whitespace_is_tidied_and_empty_text_gives_nothing():
    assert pieces("  Hello \n  there   my friend,  how ") == ["Hello there my friend,", "how"]
    assert pieces("   ") == []
    assert SpeechChunker().flush() == ""
