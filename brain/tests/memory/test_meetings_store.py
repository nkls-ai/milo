import json
import struct
from datetime import datetime

import numpy as np

from milo.core.meetings import MeetingInfo, MeetingNotes, Track, TranscriptLine
from milo.memory.meetings import FileMeetingStore, JsonVoiceBook, read_wav, write_wav

SR = 16_000
INFO = MeetingInfo("Weekly sync", datetime(2026, 10, 30, 14, 0), "Zoom", ("Anna",))


def line(start, text, track=Track.THEM, speaker="S1"):
    return TranscriptLine(start, start + 1, track, speaker, text)


def test_open_makes_a_folder_per_meeting_with_a_readable_id(tmp_path):
    store = FileMeetingStore(tmp_path)
    first, second = store.open(INFO), store.open(INFO)
    assert first == "2026-10-30-1400-weekly-sync" and second == "2026-10-30-1400-weekly-sync-2"
    assert store.audio_dir(first).is_dir() and store.info(first) == INFO
    assert store.unfinished() == [first, second]


def test_lines_count_only_once_their_progress_mark_is_written(tmp_path):
    store = FileMeetingStore(tmp_path)
    id = store.open(INFO)
    store.append(id, [line(0, "hello"), line(2, "there")], track=Track.THEM, upto=27.5)
    store.append(id, [line(1, "hi", Track.ME, "me")], track=Track.ME, upto=29.0)
    # A crash in the middle of the next pass: two lines written, the mark and part of a line not.
    with open(tmp_path / id / "transcript.jsonl", "a") as f:
        f.write(json.dumps(line(30, "lost").to_dict()) + "\n" + '{"start": 31, "end"')
    assert [l.text for l in store.lines(id)] == ["hello", "there", "hi"]
    assert store.progress(id) == {Track.ME: 29.0, Track.THEM: 27.5}
    # The pass runs again after the restart, and its lines count once.
    store.append(id, [line(30, "lost")], track=Track.THEM, upto=55.0)
    assert [l.text for l in store.lines(id)] == ["hello", "there", "hi", "lost"]


def test_chunks_read_up_to_the_last_sample_even_with_a_header_a_crash_never_fixed(tmp_path):
    store = FileMeetingStore(tmp_path)
    id = store.open(INFO)
    folder = store.audio_dir(id)
    write_wav(folder / "them-0001.wav", np.full(30 * SR, 0.25, np.float32))
    write_wav(folder / "them-0002.wav", np.full(10 * SR, -0.5, np.float32))
    # The app crashed while writing chunk 3: its header still says zero bytes.
    data = (np.full(4 * SR, 0.1) * 32767).astype("<i2").tobytes()
    header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", 36, b"WAVE", b"fmt ", 16, 1, 1, SR, SR * 2, 2, 16, b"data", 0)
    (folder / "me-0001.wav").write_bytes(header + data)
    (folder / "notes.txt").write_text("not a chunk", encoding="utf-8")
    chunks = store.chunks(id)
    assert [(c.track, c.index, c.start, c.seconds) for c in chunks] == [
        (Track.ME, 1, 0.0, 4.0), (Track.THEM, 1, 0.0, 30.0), (Track.THEM, 2, 30.0, 10.0)]
    assert len(read_wav(folder / "me-0001.wav")) == 4 * SR
    audio = store.audio(id, Track.THEM, 29.0, 31.0)
    assert len(audio) == 2 * SR
    assert np.allclose(audio[:SR], 0.25, atol=1e-3) and np.allclose(audio[SR:], -0.5, atol=1e-3)


def test_a_missing_chunk_is_silence_so_times_stay_right(tmp_path):
    store = FileMeetingStore(tmp_path)
    id = store.open(INFO)
    write_wav(store.audio_dir(id) / "me-0002.wav", np.full(30 * SR, 0.5, np.float32))
    audio = store.audio(id, Track.ME, 20.0, 40.0)
    assert len(audio) == 20 * SR and not audio[:10 * SR].any() and audio[10 * SR:].min() > 0.4


def test_close_writes_the_notes_and_deletes_the_audio_unless_kept(tmp_path):
    store = FileMeetingStore(tmp_path)
    gone, kept = store.open(INFO), store.open(INFO)
    for id in (gone, kept):
        write_wav(store.audio_dir(id) / "me-0001.wav", np.zeros(SR, np.float32))
    path = store.close(gone, MeetingNotes("We agreed."), "# Weekly sync\n")
    store.close(kept, MeetingNotes("Kept."), "# Weekly sync\n", keep_audio=True)
    assert path.read_text(encoding="utf-8") == "# Weekly sync\n"
    assert not store.audio_dir(gone).exists() and store.audio_dir(kept).exists()
    assert store.unfinished() == []
    assert json.loads((tmp_path / gone / "meeting.json").read_text(encoding="utf-8"))["notes"]["summary"] == "We agreed."


def test_state_is_kept_between_stores(tmp_path):
    id = FileMeetingStore(tmp_path).open(INFO)
    FileMeetingStore(tmp_path).save_state(id, {"names": {"S1": "Anna"}, "stopped": True})
    assert FileMeetingStore(tmp_path).state(id) == {"names": {"S1": "Anna"}, "stopped": True}


def test_a_broken_meeting_file_doesnt_stop_the_others(tmp_path):
    store = FileMeetingStore(tmp_path)
    ok = store.open(INFO)
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "meeting.json").write_text("{", encoding="utf-8")
    assert store.unfinished() == [ok]


def test_the_voice_book_knows_a_voice_again_and_only_for_its_own_model(tmp_path):
    book = JsonVoiceBook(tmp_path / "voices.json", "titanet_small")
    anna = np.array([1.0, 0.1, 0.0])
    assert book.match(anna) is None
    book.learn("Anna", anna)
    book.learn("anna", np.array([0.9, 0.2, 0.0]))
    assert book.match(np.array([1.0, 0.15, 0.0])) == "Anna"
    assert book.match(np.array([0.0, 1.0, 0.0])) is None
    assert JsonVoiceBook(tmp_path / "voices.json", "eres2net").match(anna) is None
    voices = json.loads((tmp_path / "voices.json").read_text(encoding="utf-8"))["voices"]
    assert len(voices) == 1 and voices[0]["count"] == 2
