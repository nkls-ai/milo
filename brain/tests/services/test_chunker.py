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


def test_first_piece_goes_at_the_first_clause_with_five_words():
    chunker = SpeechChunker()
    chunker.add("Well, I think that")
    assert chunker.next() is None
    chunker.add(" is right, yes")
    assert chunker.next() == "Well, I think that is right,"


def test_first_piece_skips_boundaries_before_three_words():
    assert pieces("Sure! Let me check that for you. ", "It is nine.") == [
        "Sure! Let me check that for you.", "It is nine."]
    assert pieces("I'm doing well, thanks, just sitting here. ", "And you?") == [
        "I'm doing well, thanks, just sitting here.", "And you?"]


def test_first_piece_after_twelve_words_without_punctuation():
    chunker = SpeechChunker()
    chunker.add("one two three four five six seven eight nine ten eleven twelve")
    assert chunker.next() is None, "the twelfth word may not be done"
    chunker.add(" thirteen")
    assert chunker.next() == "one two three four five six seven eight nine ten eleven twelve"
    assert chunker.next(final=True) == "thirteen"


def test_a_big_budget_takes_everything_up_to_the_furthest_boundary():
    chunker = SpeechChunker()
    chunker.add("Hi there, here you go, this is one. This is two! And thr")
    assert chunker.next() == "Hi there, here you go,"
    assert chunker.next(200) == "this is one. This is two!"
    assert chunker.next(200) is None, "waits for the rest of the sentence"
    assert chunker.next(200, final=True) == "And thr"


def test_a_small_budget_takes_the_boundary_that_fits():
    chunker = SpeechChunker()
    chunker.add("Okay then, here you go, the first part goes right here, then comes a second part, and then the end. ")
    chunker.next()
    assert chunker.next(60) == "the first part goes right here, then comes a second part,"
    assert chunker.next(60) is None, "the sentence end needs the next word"
    assert chunker.next(60, final=True) == "and then the end."


def test_a_boundary_a_little_past_the_budget_beats_a_mid_clause_cut():
    chunker = SpeechChunker()
    chunker.add("Okay then, here you go, the fridge moves the heat from inside to outside, ")
    chunker.next()
    assert chunker.next(50) == "the fridge moves the heat from inside to outside,"


def test_text_past_the_budget_waits_for_a_boundary_rather_than_cut_mid_clause():
    chunker = SpeechChunker()
    chunker.add("Okay then, here you go, just don't make me so smart I start giving opinions about ")
    chunker.next()
    assert chunker.next(45) is None, "a cut here would sound like Milo was cut off"
    chunker.add("your bedtime. And")
    assert chunker.next(45) == "just don't make me so smart I start giving opinions about your bedtime."


def test_text_past_the_cap_without_a_boundary_cuts_on_a_space():
    chunker = SpeechChunker()
    chunker.add("Okay then, here you go, " + "word " * 50)
    chunker.next()
    piece = chunker.next(60)
    assert piece is not None and len(piece) <= 60 and piece.endswith("word")


def test_the_budget_never_drops_below_the_minimum():
    chunker = SpeechChunker()
    chunker.add("Okay then, here you go, alpha beta gamma delta epsilon zeta eta theta. Next")
    chunker.next()
    assert chunker.next(0) == "alpha beta gamma delta epsilon zeta eta theta.", f"{MIN_BUDGET} chars plus overshoot"


def test_a_sentence_end_waits_for_the_next_word():
    chunker = SpeechChunker()
    chunker.add("Hi there, here you go, ")
    chunker.next()
    chunker.add("this is one.")
    assert chunker.next(200) is None
    chunker.add(" ")
    assert chunker.next(200) is None
    chunker.add("Next")
    assert chunker.next(200) == "this is one."


def test_decimals_and_abbreviations_do_not_split():
    assert pieces("Hello, here you all go, ", "version 2.5 is out e.g. today. Nice", budget=MIN_BUDGET) == [
        "Hello, here you all go,", "version 2.5 is out e.g. today.", "Nice"]


def test_pieces_never_exceed_the_cap_and_keep_every_word():
    text = "a b c d e f g h i j k l " + "y" * 10 + " " + "z " * 200
    out = pieces(text)
    assert out[0] == "a b c d e f g h i j k l"
    assert all(len(p) <= MAX_CHARS for p in out)
    assert " ".join(out).split() == text.split()


def test_whitespace_is_tidied_and_empty_text_gives_nothing():
    assert pieces("  Hello \n  there   my  good old friend,  how ") == ["Hello there my good old friend,", "how"]
    assert pieces("   ") == []
    assert SpeechChunker().flush() == ""


def sentences(*deltas: str) -> list[str]:
    chunker = SpeechChunker(sentences=True)
    out = []
    for d in deltas:
        chunker.add(d)
        while (p := chunker.next()) is not None:
            out.append(p)
    while (p := chunker.next(final=True)) is not None:
        out.append(p)
    return out


def test_for_a_streaming_voice_pieces_are_whole_sentences_never_clauses():
    assert sentences("Klar, ", "mach ich. Morgen um zehn, ", "dann frei. Oh, and ", "lunch") == [
        "Klar, mach ich.", "Morgen um zehn, dann frei.", "Oh, and lunch"]
    assert sentences("One. Two. Three. Fo", "ur") == ["One. Two. Three.", "Four"], "every whole sentence at once"
    assert sentences("Version 2.5 is out, e.g. today. Nice") == ["Version 2.5 is out, e.g. today.", "Nice"]


def test_a_sentence_too_long_for_one_piece_is_cut_at_its_last_clause():
    long = "word " * 40 + "and then, " + "more " * 10 + "end. Next"
    out = sentences(long)
    assert len(out[0]) <= MAX_CHARS and out[0].endswith("then,")
    assert " ".join(out).split() == long.split()
