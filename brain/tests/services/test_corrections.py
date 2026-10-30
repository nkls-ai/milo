"""Learning from the user's fixes and applying them before the paste (ADR 21)."""

from milo.adapters.text.fillers import FillerCleaner
from milo.core.events import Dictation, Status
from milo.services.corrections import MAX_PER_PASTE, Corrections, DictationFixes
from milo.services.dictation import DictationService
from tests.fakes import ListVocabulary, MemoryDictionary, RecordingSink


def test_a_fix_is_learned_noted_once_and_sent_to_the_transcribers():
    dictionary, sink, whisper = MemoryDictionary(), RecordingSink(), ListVocabulary()
    corrections = Corrections(dictionary, sink, [whisper])
    corrections.fixed([("Cloud Code", "Claude Code")])
    assert sink.of(Status) == [Status("Learned: Claude Code")]
    assert whisper.words == [["Claude Code"]]
    corrections.fixed([("Cloud Code", "Claude Code")])
    assert sink.of(Status) == [Status("Learned: Claude Code")], "seen again: no second note"
    assert "- Cloud Code -> Claude Code (seen 2)" in dictionary.markdown


def test_no_note_while_milo_is_busy_but_the_fix_is_kept():
    dictionary, sink = MemoryDictionary(), RecordingSink()
    Corrections(dictionary, sink, busy=lambda: True).fixed([("Nicholas", "Niklas")])
    assert sink.of(Status) == []
    assert "Nicholas -> Niklas" in dictionary.markdown


def test_off_learns_nothing():
    dictionary, sink = MemoryDictionary(), RecordingSink()
    corrections = Corrections(dictionary, sink, enabled=False)
    corrections.fixed([("Nicholas", "Niklas")])
    assert dictionary.learned == [] and sink.events == []


def test_at_most_a_few_fixes_per_paste():
    dictionary = MemoryDictionary()
    Corrections(dictionary, RecordingSink()).fixed([(f"Nick{i}", f"Nik{i}") for i in range(20)])
    assert len(dictionary.learned) == MAX_PER_PASTE


def test_undoing_a_replacement_says_nothing():
    dictionary, sink = MemoryDictionary("## Fixes\n- Cloud Code -> Claude Code (seen 1)\n"), RecordingSink()
    Corrections(dictionary, sink).fixed([("Claude Code", "Cloud Code")])
    assert sink.events == [] and "Claude" not in dictionary.markdown


def test_refresh_sends_the_words_only_when_the_file_changed():
    dictionary, whisper = MemoryDictionary("## Words\n- Milo\n"), ListVocabulary()
    corrections = Corrections(dictionary, RecordingSink(), [whisper])
    corrections.refresh()
    corrections.refresh()
    assert whisper.words == [["Milo"]]
    dictionary.markdown += "- Anna\n"  # the user edits the file
    corrections.refresh()
    assert whisper.words[-1] == ["Milo", "Anna"]


def test_fixes_apply_after_the_cleaner_and_before_the_paste():
    dictionary = MemoryDictionary("## Fixes\n- Cloud Code -> Claude Code (seen 1)\n- cloud -> Claude (seen 1)\n")
    sink = RecordingSink()
    service = DictationService(DictationFixes(FillerCleaner(["en"]), dictionary), None, sink)
    assert service.handle("um I set up Cloud Code in the cloud", None) == "I set up Claude Code in the cloud"
    assert sink.of(Dictation) == [Dictation("I set up Claude Code in the cloud")]


def test_typed_dictation_fixes_every_phrase():
    dictionary = MemoryDictionary("## Fixes\n- Nicholas -> Niklas (seen 1)\n")
    sink = RecordingSink()
    typed = DictationService(DictationFixes(FillerCleaner(["en"]), dictionary), None, sink).typed()
    typed.add("Hi Nicholas,")
    typed.add("thanks Nicholas.")
    assert [e.text for e in sink.of(Dictation)] == ["Hi Niklas,", " thanks Niklas."]


def test_a_fix_learned_while_milo_runs_applies_to_the_next_paste():
    dictionary = MemoryDictionary()
    cleaner = DictationFixes(FillerCleaner(["en"]), dictionary)
    assert cleaner.clean("Cloud Code") == "Cloud Code"
    Corrections(dictionary, RecordingSink()).fixed([("Cloud Code", "Claude Code")])
    assert cleaner.clean("Cloud Code") == "Claude Code"
