"""Dictation end to end, on every gate: a real brain process hears recorded "speech" over the WAV microphone
and is driven over its socket like the app drives it. Tones stand in for words and for Whisper (see
milo.adapters.stt.tones), so it needs no model and checks every word. scripts/e2e-dictation.sh runs the same
with Whisper on `say` voices."""

import asyncio
import shutil
import tempfile
from pathlib import Path

import numpy as np

from milo.adapters.stt.tones import ToneCodec
from milo.eval import dictation as e2e

GATE = [c for c in e2e.CASES if c.id in e2e.GATE]


def test_dictation_end_to_end_loses_no_words_and_stays_fast():
    root = Path(tempfile.mkdtemp(prefix="milo-e2e-", dir="/tmp"))  # short: a socket path has 104 bytes at most

    async def each_in_its_own_brain():  # in parallel: the recordings play in real time
        return await asyncio.gather(*(e2e.run([case], root / case.id, fake=True, streams=("preview", "type"))
                                      for case in GATE))

    try:
        runs = [run for case_runs in asyncio.run(each_in_its_own_brain()) for run in case_runs]
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(e2e.table(runs))
    assert {r.case for r in runs} == set(e2e.GATE)
    assert [f"{r.case} {r.stream}: {'; '.join(r.problems)}" for r in runs if r.problems] == []
    assert all(r.errors == 0 for r in runs), "the tone transcriber hears every word, so dictation must too"


def test_the_gate_holds_each_way_words_were_lost():
    by_id = {c.id: c for c in GATE}
    assert by_id["en-release-after-pause"].release_s <= 0.1, "let go right after words that followed a pause"
    assert any(p.level <= 0.1 for p in by_id["de-soft-tail"].parts), "trailing off softly"
    assert by_id["en-15s-quiet-mic"].mic <= 0.1, "a quiet microphone"


def test_tones_are_heard_back_as_the_words_at_any_level():
    codec = ToneCodec(e2e.vocabulary())
    case = next(c for c in e2e.CASES if c.id == "de-15s")
    for level in (0.08, 0.004):
        audio = codec.speak(" ".join(e2e.words(case.script)), level)
        audio = audio + np.random.default_rng(0).normal(0, 0.0015, len(audio)).astype(np.float32)
        assert codec.hear(audio) == e2e.words(case.script)


def test_word_errors_count_what_is_missing():
    assert e2e.align("a b c d".split(), "a c d".split()) == (0, 1, 0)
    assert e2e.align("a b c".split(), "a x c e".split()) == (1, 0, 1)
    assert e2e.words("Klingt gut, bis morgen-früh!") == ["klingt", "gut", "bis", "morgen", "früh"]


def test_runs_fail_on_lost_words_slow_pastes_and_missing_live_words():
    off = e2e.Run("c", "en", 5.0, "off", errors=1, lost=1, words=10)
    good = e2e.Run("c", "en", 5.0, "preview", paste_s=0.1, first_partial_s=0.4, state_s=0.09, errors=1, lost=1,
                   words=10)
    bad = e2e.Run("c", "en", 5.0, "preview", text="x", paste_s=0.9, first_partial_s=None, state_s=0.3, errors=4,
                  lost=3, words=10)
    e2e.check([off, good, bad], e2e.FAKE)
    assert good.problems == []
    assert len(bad.problems) == 5, bad.problems
